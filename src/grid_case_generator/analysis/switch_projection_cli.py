"""Run E2.2 counterfactual design experiments over verified E1/E2 artifacts."""
import argparse
from grid_case_generator.analysis.switch_projection_proposal import render_proposal
from grid_case_generator.io.switch_projection_artifacts import run_projection_analysis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    def progress(index, total, result):
        if index % 100 == 0 or index == total:
            print(f'E2.2 {index}/{total}: {result["case_id"]}', flush=True)
    reports = run_projection_analysis(args.source, args.baseline, args.output, render_proposal, progress=progress)
    print(reports['coverage_by_strategy']['strategies'], flush=True)


if __name__ == '__main__': main()
