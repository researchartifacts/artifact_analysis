#!/usr/bin/env python3
"""
Export artifact citations in a simple format showing artifact DOI and citing DOIs.

Usage:
    python3 export_artifact_citations.py --data_dir ../researchartifacts.github.io
    python3 export_artifact_citations.py --data_dir ../researchartifacts.github.io --output citations_export.txt
"""

import json
import os
import sys
import argparse


def export_citations(data_dir: str, output_file: str = None) -> None:
    """Export artifact citations to a simple DOI mapping format."""
    
    citations_path = os.path.join(data_dir, "assets", "data", "artifact_citations.json")
    
    if not os.path.exists(citations_path):
        print(f"Error: {citations_path} not found.", file=sys.stderr)
        print("Run generate_artifact_citations.py first.", file=sys.stderr)
        sys.exit(1)
    
    with open(citations_path, "r") as f:
        artifacts = json.load(f)
    
    # Open output file or use stdout
    out = open(output_file, "w") if output_file else sys.stdout
    
    try:
        artifacts_with_citations = 0
        total_citing_dois = 0
        
        for artifact in artifacts:
            doi = artifact.get("doi")
            if not doi:
                continue
            
            # Collect citing DOIs from both sources
            citing_dois = []
            
            # Add OpenAlex citing DOIs
            openalex_citing = artifact.get("citing_dois_openalex", [])
            if openalex_citing:
                citing_dois.extend(openalex_citing)
            
            # Add Semantic Scholar citing DOIs
            semantic_citing = artifact.get("citing_dois_semantic_scholar", [])
            if semantic_citing:
                citing_dois.extend(semantic_citing)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_citing_dois = []
            for citing_doi in citing_dois:
                if citing_doi not in seen:
                    seen.add(citing_doi)
                    unique_citing_dois.append(citing_doi)
            
            # Only output if there are citations
            if unique_citing_dois:
                artifacts_with_citations += 1
                total_citing_dois += len(unique_citing_dois)
                
                # Format: artifact_doi: ["citing_doi_1", "citing_doi_2", ...]
                citing_dois_str = json.dumps(unique_citing_dois)
                out.write(f"{doi}: {citing_dois_str}\n")
        
        # Print summary to stderr so it doesn't interfere with output
        print(f"\n# Summary:", file=sys.stderr)
        print(f"# Total artifacts with DOIs: {sum(1 for a in artifacts if a.get('doi'))}", file=sys.stderr)
        print(f"# Artifacts with citing DOIs: {artifacts_with_citations}", file=sys.stderr)
        print(f"# Total citing DOIs collected: {total_citing_dois}", file=sys.stderr)
        
    finally:
        if output_file:
            out.close()
            print(f"\nWrote citations export to: {output_file}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Export artifact citations as DOI mappings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Output to stdout
  python3 export_artifact_citations.py --data_dir ../researchartifacts.github.io
  
  # Output to file
  python3 export_artifact_citations.py --data_dir ../researchartifacts.github.io --output citations.txt
  
  # Pipe to other tools
  python3 export_artifact_citations.py --data_dir ../researchartifacts.github.io | grep "10.5281/zenodo"
        """
    )
    
    parser.add_argument(
        "--data_dir",
        required=True,
        help="Path to the website data directory (e.g., ../researchartifacts.github.io)"
    )
    
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: stdout)"
    )
    
    args = parser.parse_args()
    
    export_citations(args.data_dir, args.output)


if __name__ == "__main__":
    main()
