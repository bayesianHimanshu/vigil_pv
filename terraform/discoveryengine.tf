###############################################################################
# Vertex AI Search (Discovery Engine) - the grounding corpus for MedDRA PTs and
# the data surface Gemini Enterprise points at.
#
# NOTE: the default pipeline grounds in-process (vigil/grounding.py
# EmbeddingGrounder), so this data store is the *production swap* target
# referenced in grounding.py / README ("swap the embedding grounder for a Vertex
# AI Search datastore - same Grounder interface"). It is pay-per-use; the LLM
# search engine on top is gated separately to avoid the add-on cost.
###############################################################################

resource "google_discovery_engine_data_store" "meddra" {
  count = var.enable_vertex_ai_search ? 1 : 0

  project           = var.project_id
  location          = var.discovery_location
  data_store_id     = "vigil-meddra-pt"
  display_name      = "VIGIL MedDRA PT grounding corpus"
  industry_vertical = "GENERIC"
  solution_types    = ["SOLUTION_TYPE_SEARCH"]
  content_config    = "NO_CONTENT" # structured term list, not documents

  depends_on = [time_sleep.after_apis]
}

resource "google_discovery_engine_search_engine" "meddra" {
  count = var.enable_vertex_ai_search && var.enable_search_engine ? 1 : 0

  project        = var.project_id
  engine_id      = "vigil-meddra-search"
  collection_id  = "default_collection"
  location       = var.discovery_location
  display_name   = "VIGIL MedDRA search"
  data_store_ids = [google_discovery_engine_data_store.meddra[0].data_store_id]

  search_engine_config {
    search_tier    = "SEARCH_TIER_STANDARD"
    search_add_ons = ["SEARCH_ADD_ON_LLM"]
  }
}
