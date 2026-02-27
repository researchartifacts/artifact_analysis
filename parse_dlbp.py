# Based on https://github.com/HexHive/pubstats/blob/master/parse_dblp.py

import lxml.etree as ET
from gzip import GzipFile
import pickle
import csv
import re

def normalize_title(title):
    return title.strip().lower() if title else ""

def parse_dblp_xml(dblp_file, paper_titles):
    """
    Parse the DBLP XML file and extract relevant information.
    """
    dblp_stream = GzipFile(filename=dblp_file)
    it = 0
    for event, elem in ET.iterparse(dblp_stream, events = ('end', ), tag=('inproceedings', 'article'), load_dtd = True):
        if normalize_title(elem.findtext('title')[:-1]) in paper_titles:
            [print(f"{child.tag}: {child.text}") for child in elem]
            yield {
                'title': elem.findtext('title'),
                'authors': [a.text for a in elem.findall('author')],
                'year': elem.findtext('year'),
                'venue': elem.findtext('booktitle')
            }
            # break after finding all papers
            paper_titles.remove(normalize_title(elem.findtext('title')[:-1]))  # Remove title to avoid duplicates
            if not paper_titles:
                break
        it += 1
        if it % 10000 == 0:
            print(f'Processed {it} elements...')

        elem.clear()  # Clear the root to save memory

    if paper_titles:
        print(f'Could not find {paper_titles} in DBLP XML file.')
    dblp_stream.close()

def main():
    xml_file = 'dblp.xml.gz'  # Path to the DBLP XML file

    # Parse the DBLP XML file
    dblp_data = list(parse_dblp_xml(xml_file, set(map(normalize_title, ["JABAS: Joint Adaptive Batching and Automatic Scaling for DNN Training on Heterogeneous GPUs"]))))

    print(f"Parsed {len(dblp_data)} {dblp_data}")

if __name__ == '__main__':
    main()