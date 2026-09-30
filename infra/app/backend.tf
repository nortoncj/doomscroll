# Same bucket as bootstrap, different key. The ci-apply role can only
# write under app/, so this stack can never clobber bootstrap's state.
terraform {
  backend "s3" {
    bucket       = "doomscroll-tfstate-205207086306"
    key          = "app/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}