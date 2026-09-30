###############################################################################
# Leave this commented out for the FIRST apply.
#
# The bucket doesn't exist yet, so bootstrap starts with local state. After
# the first apply:
#   1. Uncomment the block below
#   2. Replace the bucket name with the state_bucket_name output
#      (backend blocks can't use variables, so it has to be hardcoded)
#   3. Run: terraform init -migrate-state
#   4. Type "yes" when it asks to copy state to S3
#   5. Delete the local terraform.tfstate files once you confirm the object is in S3
###############################################################################

terraform {
   backend "s3" {
     bucket       = "doomscroll-tfstate-205207086306"
     key          = "bootstrap/terraform.tfstate"
     region       = "us-east-1"
     encrypt      = true
     use_lockfile = true
   }
 }
