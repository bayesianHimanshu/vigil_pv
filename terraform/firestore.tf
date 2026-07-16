###############################################################################
# Firestore (Native) - low-latency, mutable case workflow state.
# Collections: cases/{vaers_id}, cases/{vaers_id}/events/{event_id},
#              pipeline_versions/{version}   (see sql/data_model.sql ZONE notes)
###############################################################################

resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.firestore_location
  type        = "FIRESTORE_NATIVE"

  # Guard against accidental deletion of the live workflow store.
  delete_protection_state = "DELETE_PROTECTION_ENABLED"
  deletion_policy         = "ABANDON"

  depends_on = [time_sleep.after_apis]
}

# Composite index backing the reviewer's "open cases, lowest confidence first"
# query: where current_status == 'in_review' order by overall_confidence asc.
resource "google_firestore_index" "review_queue" {
  count = var.create_firestore_indexes ? 1 : 0

  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "cases"

  fields {
    field_path = "current_status"
    order      = "ASCENDING"
  }
  fields {
    field_path = "overall_confidence"
    order      = "ASCENDING"
  }
  fields {
    field_path = "__name__"
    order      = "ASCENDING"
  }
}
