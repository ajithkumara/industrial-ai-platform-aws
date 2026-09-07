# Placeholder for future predictive/ML feature engineering (Gold layer).
#
# NOT a registered DLT table and NOT included in
# databricks/resources/pipelines/dlt.yml's `libraries:` — intentionally
# excluded from the active pipeline. Previously carried a `@dlt.table(...)`
# decorator with a `pass` body, which made this look like a live, deployed
# Gold table on inspection even though it was never wired into the
# pipeline. Removed the decorator so the file's status as unimplemented
# scaffolding is unambiguous. Add the decorator back only once this is a
# real implementation and it has been added to dlt.yml's libraries list.


def predictive_features():
    """Not implemented. Placeholder for future Gold-layer predictive features."""
    raise NotImplementedError(
        "predictive_features is scaffolding only and is not part of the "
        "active DLT pipeline. See databricks/resources/pipelines/dlt.yml."
    )
