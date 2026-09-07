output "trail_arn" { value = aws_cloudtrail.this.arn }
output "trail_bucket" { value = aws_s3_bucket.trail.id }
