# economics

## Repository setup

If `git remote -v` prints no output, no remotes are configured yet.

Configure a default `origin` remote with your repository URL:

```bash
git remote add origin <your-repo-url>
```

Verify:

```bash
git remote -v
```


## Paper build

Build the Bihar manuscript PDF:

```bash
./paper/build_paper.sh
```

- The script first regenerates the LaTeX source using `paper/generate_bihar_paper.py`.
- If `pdflatex` is available and succeeds, it performs a 2-pass LaTeX build.
- If `pdflatex` is unavailable **or compilation fails**, it falls back to `paper/generate_bihar_paper_pdf.py` and still produces `paper/Bihar_Macroeconomic_Growth_Research_Paper.pdf`.
