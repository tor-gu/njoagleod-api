#!/usr/bin/env Rscript
# Export the njoagleod tables to gzipped CSV, the input of scripts/build_data.py,
# and R's own counts for the parity test.
#
# Usage: Rscript scripts/export_data.R <git-ref> [out-dir] [expected-dir]
#
# Installs tor-gu/njoagleod at <git-ref> (e.g. v2.0.0) into a temporary library,
# with its hard dependencies, and writes to out-dir (default: data):
#   <table>.csv.gz  one per table, in R's row order (NA is an empty field; a logical
#                   is TRUE or FALSE)
#   columns.csv     table, position, column, type (integer, logical, factor or
#                   character)
#   levels.csv      table, column, position, level (every factor column)
#   SOURCE          the release and commit
# and to expected-dir (default: tests/parity/expected), gzipped:
#   counts_<table>.csv.gz  dplyr::count(<table>, <by...>, wt = <table>_count) for
#                          each by in by_sets(): a by column ("year,officer_race"),
#                          the table's key columns (NA where not in by or NA in R)
#                          and count, in R's order
#
# To export a tag that isn't pushed yet, set NJOAGLEOD_GIT to a local clone, e.g.
# NJOAGLEOD_GIT=../../njoagleod/njoagleod.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1 || length(args) > 3) {
  stop("Usage: Rscript scripts/export_data.R <git-ref> [out-dir] [expected-dir]")
}
ref <- args[[1]]
out_dir <- if (length(args) >= 2) args[[2]] else "data"
expected_dir <- if (length(args) >= 3) args[[3]] else file.path("tests", "parity", "expected")

tables <- c("officer", "applicant", "agency_practice")
count_tables <- c("officer", "applicant")

lib <- file.path(tempdir(), "njoagleod-lib")
dir.create(lib, showWarnings = FALSE)
# njoagleod imports njlea (and so njmunicipalities and dplyr). Missing hard
# dependencies are installed into lib too (from Remotes); installed ones are
# used as they are.
.libPaths(c(lib, .libPaths()))
local_git <- Sys.getenv("NJOAGLEOD_GIT")
if (nzchar(local_git)) {
  remotes::install_git(
    paste0("file://", normalizePath(local_git)),
    ref = ref, lib = lib, upgrade = "never", dependencies = NA, quiet = TRUE
  )
} else {
  remotes::install_github(
    "tor-gu/njoagleod",
    ref = ref, lib = lib, upgrade = "never", dependencies = NA, quiet = TRUE
  )
}
desc <- packageDescription("njoagleod", lib.loc = lib)
commit <- if (!is.null(desc$RemoteSha)) desc$RemoteSha else NA

column_type <- function(col) {
  if (is.factor(col)) {
    "factor"
  } else if (is.logical(col)) {
    "logical"
  } else if (is.integer(col)) {
    "integer"
  } else if (is.numeric(col)) {
    if (any(!is.na(col) & col != round(col))) {
      stop("numeric column with non-integer values")
    }
    "integer"
  } else if (is.character(col)) {
    if (any(!is.na(col) & col == "")) {
      stop("empty string, which the CSV can't tell from NA")
    }
    "character"
  } else {
    stop("unexpected column class ", class(col)[[1]])
  }
}

# Writes df gzipped, with gzip -n so the same data gives the same bytes
write_csv_gz <- function(df, path) {
  csv <- sub("\\.gz$", "", path)
  write.csv(as.data.frame(df), csv, row.names = FALSE, na = "", fileEncoding = "UTF-8")
  unlink(path)
  status <- system2("gzip", c("-n", "-9", shQuote(csv)))
  if (status != 0) stop("gzip failed for ", csv)
  message("Wrote ", nrow(df), " rows to ", path)
}

# Writes df as <name>.csv.gz, and returns its columns.csv and levels.csv rows
export_table <- function(df, name) {
  df <- as.data.frame(df)
  types <- vapply(
    names(df),
    function(column) {
      tryCatch(column_type(df[[column]]), error = function(e) {
        stop(name, ".", column, ": ", conditionMessage(e))
      })
    },
    character(1)
  )
  levels_out <- list()
  for (column in names(df)) {
    col <- df[[column]]
    if (is.factor(col)) {
      if ("" %in% levels(col)) stop(name, ".", column, ": has an empty factor level")
      lv <- levels(col)
      levels_out[[length(levels_out) + 1]] <- data.frame(
        table = name, column = column, position = seq_along(lv), level = lv
      )
    }
    if (types[[column]] == "integer" && !is.integer(col)) {
      df[[column]] <- as.integer(col)
    }
  }
  write_csv_gz(df, file.path(out_dir, paste0(name, ".csv.gz")))
  list(
    columns = data.frame(table = name, position = seq_along(types),
                         column = names(df), type = types),
    levels = do.call(rbind, levels_out)
  )
}

# The groupings the parity test compares: each key column, year with each other
# one, and the four-column grouping the API's by limit is set for
by_sets <- function(keys) {
  others <- setdiff(keys, "year")
  race <- grep("_race$", keys, value = TRUE)
  gender <- grep("_gender$", keys, value = TRUE)
  c(
    as.list(keys),
    lapply(others, function(k) c("year", k)),
    list(c("year", "agency_id", race, gender))
  )
}

# R's counts for every grouping, stacked, as strings as write.csv would write them
export_counts <- function(df, name) {
  weight <- paste0(name, "_count")
  keys <- setdiff(names(df), weight)
  out <- lapply(by_sets(keys), function(by) {
    counted <- dplyr::count(df, dplyr::across(dplyr::all_of(by)),
                            wt = .data[[weight]], name = "count")
    counted <- as.data.frame(counted)
    row <- data.frame(by = rep(paste(by, collapse = ","), nrow(counted)))
    for (k in keys) {
      row[[k]] <- if (k %in% by) as.character(counted[[k]]) else NA_character_
    }
    row$count <- counted$count
    row
  })
  write_csv_gz(do.call(rbind, out), file.path(expected_dir, paste0("counts_", name, ".csv.gz")))
}

dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
dir.create(expected_dir, showWarnings = FALSE, recursive = TRUE)

exported <- list()
for (name in tables) {
  env <- new.env()
  data(list = name, package = "njoagleod", lib.loc = lib, envir = env)
  exported[[name]] <- export_table(env[[name]], name)
  if (name %in% count_tables) {
    export_counts(env[[name]], name)
  }
}

write.csv(do.call(rbind, lapply(exported, `[[`, "columns")),
          file.path(out_dir, "columns.csv"), row.names = FALSE, fileEncoding = "UTF-8")
write.csv(do.call(rbind, lapply(exported, `[[`, "levels")),
          file.path(out_dir, "levels.csv"), row.names = FALSE, fileEncoding = "UTF-8")

source_lines <- c(
  "package=njoagleod",
  paste0("version=", desc$Version),
  paste0("ref=", ref),
  paste0("commit=", commit),
  paste0("exported=", format(Sys.Date()))
)
writeLines(source_lines, file.path(out_dir, "SOURCE"))
message("Wrote ", file.path(out_dir, "SOURCE"))
