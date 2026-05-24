#!/bin/bash

# Build script for Mintlify documentation
# Supports both Netlify and Vercel deployment

set -e

echo "Building Mintlify documentation..."

cd mintlify-docs

# Install dependencies
npm install

# Try to export static site
echo "Attempting to export Mintlify..."

if npm run build; then
  echo "Build successful"
  # Check for output directories
  if [ -d ".mintlify" ]; then
    echo "Found .mintlify directory"
    mkdir -p ../public
    cp -r .mintlify/* ../public/ || cp -r .mintlify ../public/
  elif [ -d "dist" ]; then
    echo "Found dist directory"
    mkdir -p ../public
    cp -r dist/* ../public/ || cp -r dist ../public/
  elif [ -d ".next" ]; then
    echo "Found .next directory (Next.js build)"
    mkdir -p ../public
    cp -r .next ../public/ || true
    [ -d "public" ] && cp -r public/* ../public/ || true
  else
    echo "No standard output directory found, checking for output..."
    find . -maxdepth 2 -type d | grep -E "(dist|build|out|public|\.mintlify|\.next)" || echo "No output directories found"
  fi
else
  echo "Build command failed, using source directory as fallback"
  mkdir -p ../public
  cp -r . ../public/ || true
fi

echo "Build complete"
