import pandas as pd

# Run coding-1.ipynb and coding-2.ipynb first, they create these csv files
results = pd.concat([
    pd.read_csv("results-100k.csv"),
    pd.read_csv("results-2M.csv"),
])
experiment = pd.read_csv("chunk-size-experiment.csv")

# Put the 100k and 2M results side by side, for every section
comparison = results.pivot_table(
    index="label", columns="file", values=["peak_mb", "time_s"], sort=False
)
comparison.columns = [f"{value} ({file})" for value, file in comparison.columns]
comparison = comparison.reset_index().rename(columns={"label": "section"})
comparison = comparison.fillna("-")   # "-" = not measured for that file

# Write everything into a markdown file, so the result can be opened later
with open("coding-3-results.md", "w", encoding="utf-8") as f:
    f.write("# Coding Test #3: Small vs Large File\n\n")
    f.write("## Time & Peak Memory per Section\n\n")
    f.write("- 100k: `customers-100000.csv`, loaded at once (coding-1)\n")
    f.write("- 2M: `customers-2000000.csv`, read in chunks of 50,000 rows (coding-2)\n")
    f.write("- `(time only)` rows are measured without tracemalloc, because it makes pandas slower\n")
    f.write("- `read csv` rows in 2M load the whole file at once, only as a comparison\n\n")
    f.write(comparison.to_markdown(index=False))
    f.write("\n\n## Chunk Size Experiment (2M file)\n\n")
    f.write(experiment.to_markdown(index=False))
    f.write("\n")

print("Saved to coding-3-results.md")
