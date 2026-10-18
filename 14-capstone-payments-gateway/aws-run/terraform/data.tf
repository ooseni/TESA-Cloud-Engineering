# The payments table (ADR-0001), as the demo's setup creates it locally: claims keyed by channel and
# reference, a stream of every change for the relay, the re-query index, and time to live on expires_at.

resource "aws_dynamodb_table" "payments" {
  #checkov:skip=CKV_AWS_119:Encrypted with an AWS owned key; the design's customer managed key is listed for production.
  name             = "paygate-payments"
  billing_mode     = "PAY_PER_REQUEST"
  hash_key         = "pk"
  stream_enabled   = true
  stream_view_type = "NEW_IMAGE"

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "attn_pk"
    type = "S"
  }
  attribute {
    name = "attn_at"
    type = "N"
  }

  global_secondary_index {
    name            = "attention"
    projection_type = "ALL"
    key_schema {
      attribute_name = "attn_pk"
      key_type       = "HASH"
    }
    key_schema {
      attribute_name = "attn_at"
      key_type       = "RANGE"
    }
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }
}
