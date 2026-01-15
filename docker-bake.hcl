# docker-bake.hcl
# Docker Bake configuration for deskbird-booking

# Variables from environment
variable "VERSION" {
  default = "latest"
}

variable "REGISTRY" {
  default = "ghcr.io"
}

variable "IMAGE_NAME" {
  default = "calebsargeant/deskbird-booking"
}

variable "REPO_NAME" {
  default = "deskbird-booking"
}

variable "PLATFORMS" {
  default = "linux/amd64,linux/arm64"
}

# Default target group
group "default" {
  targets = ["deskbird-booking"]
}

# Main build target
target "deskbird-booking" {
  context    = "."
  dockerfile = "Dockerfile"

  # Multi-platform support
  platforms = split(",", PLATFORMS)

  # Tags with multiple versions
  tags = [
    "${REGISTRY}/${IMAGE_NAME}:${VERSION}",
    "${REGISTRY}/${IMAGE_NAME}:latest",
  ]

  # Labels for metadata
  labels = {
    "org.opencontainers.image.source"      = "https://github.com/CalebSargeant/${REPO_NAME}"
    "org.opencontainers.image.repo"        = "${REPO_NAME}"
    "org.opencontainers.image.version"     = "${VERSION}"
    "org.opencontainers.image.created"     = timestamp()
    "org.opencontainers.image.description" = "Deskbird Booking Automation - Automated desk booking"
  }

  # Build arguments
  args = {
    VERSION               = "${VERSION}"
    BUILDKIT_INLINE_CACHE = "1"  # Enable inline cache
  }

  # Cache configuration
  cache-from = [
    "type=registry,ref=${REGISTRY}/${IMAGE_NAME}:buildcache",
  ]

  cache-to = [
    "type=inline",
  ]

  # Output configuration
  output = ["type=image,push=true"]
}

# Group for building all services
group "all" {
  targets = ["deskbird-booking"]
}
