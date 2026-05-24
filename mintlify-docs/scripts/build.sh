#!/bin/bash

# Build script for Vercel deployment
# This script prepares Mintlify documentation for Vercel

set -e

echo "🔨 Building Mintlify documentation for Vercel..."

# Create output directory
mkdir -p .mintlify
mkdir -p public

# Copy source files to public directory (Vercel will serve this)
cp -r . public/

# Remove node_modules from public
rm -rf public/node_modules

echo "✅ Build directory prepared"
echo "📊 Files in public directory:"
ls -la public/ | head -20

echo ""
echo "✨ Mintlify documentation ready for deployment"
