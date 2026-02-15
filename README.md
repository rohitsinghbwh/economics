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

- If `pdflatex` is available, the script uses LaTeX compilation.
- If `pdflatex` is unavailable in the environment, the script falls back to `paper/generate_bihar_paper_pdf.py` and still produces `paper/Bihar_Macroeconomic_Growth_Research_Paper.pdf`.
