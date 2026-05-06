
import json
import sys
from pathlib import Path

# Add current directory to path to import the uploaded script
sys.path.append("/home/ubuntu/upload")
import ubp_noisecore_v4 as nc

def load_problems(path):
    with open(path, 'r') as f:
        data = json.load(f)
    return data.get("problems", [])

def main():
    # Load problems
    prob_set_path = "/home/ubuntu/noisecore/dev/ubp_mathnet_problem_set.json"
    expanded_set_path = "/home/ubuntu/noisecore/dev/ubp_mathnet_expanded_problems.json"
    
    problems = load_problems(prob_set_path) + load_problems(expanded_set_path)
    
    print(f"Loaded {len(problems)} problems from external sets.")
    
    # Initialize runner
    runner = nc.MathNetNoiseRunner(mode="SV")
    
    # Run problems
    results = []
    for p in problems:
        # Map fields if necessary
        p_id = p.get("id", "unknown")
        p_text = p.get("problem", "")
        p_expected = p.get("answer") or p.get("expected", "")
        p_cat = p.get("domain") or p.get("category", "unknown")
        
        print(f"Running {p_id}...")
        res = runner.run(p_id, p_text, p_expected, p_cat)
        results.append(res)
        
        tick = res["verdict"]
        print(f"  {tick} [{p_cat[:10]:10s}] {p_id}: {str(res.get('result','—'))[:40]}")

    # Summary
    summ = runner.summary()
    print("\n" + "="*50)
    print("MATHNET EXTERNAL SET SUMMARY")
    print("="*50)
    for k, v in summ.items():
        if k != "triad":
            print(f"{k:20}: {v}")
    
    # Save results
    output = {
        "summary": summ,
        "results": results
    }
    with open("mathnet_external_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to mathnet_external_results.json")

if __name__ == "__main__":
    main()
