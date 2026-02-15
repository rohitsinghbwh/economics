#!/usr/bin/env bash
set -euo pipefail

TEX_FILE="paper/Bihar_Macroeconomic_Growth_Research_Paper.tex"

if command -v pdflatex >/dev/null 2>&1; then
  echo "Using pdflatex to build PDF..."
  pdflatex -interaction=nonstopmode -halt-on-error "$TEX_FILE"
  pdflatex -interaction=nonstopmode -halt-on-error "$TEX_FILE"
  echo "Built PDF with pdflatex."
else
  echo "pdflatex not found. Using Python fallback PDF builder..."
  python3 paper/generate_bihar_paper_pdf.py
fi
