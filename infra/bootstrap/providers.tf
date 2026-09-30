provider "aws" {
  region = var.aws_region

  # Every resource in this stack gets these tags automatically.
  # Makes it obvious in the console (and in billing) what belongs to what.
  default_tags {
    tags = {
      Project   = "doomscroll"
      ManagedBy = "terraform"
      Owner     = "chris"
      Stack     = "bootstrap"
    }
  }
}
