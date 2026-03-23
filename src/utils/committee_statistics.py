import argparse
from pytrie import Trie
import json
from  thefuzz import fuzz
from sys_sec_committee_scrape import get_committees
from sys_sec_scrape import download_file

def calculate_affiliation_stats(results):
    affiliation_stats = {}
    for name in results.keys():
        for member in results[name]:
            affiliation = member['affiliation']
            if affiliation not in affiliation_stats:
                affiliation_stats[affiliation] = []
                affiliation_stats[affiliation].append(member)
            else:
                affiliation_stats[affiliation].append(member)

    return affiliation_stats

def calculate_affiliation_stats_per_year(results):
    affiliation_stats = {}
    for name in results.keys():

        for member in results[name]:
            affiliation = member['affiliation']
            if affiliation not in affiliation_stats:
                affiliation_stats[affiliation] = {}
            if name not in affiliation_stats[affiliation]:
                affiliation_stats[affiliation][name] = []
            affiliation_stats[affiliation][name].append(member)

    return affiliation_stats

def aec_retention(results):
    conf_mem_set = {}
    for conf in results.keys():
        conf_mem_set[conf] = {}
        for member in results[conf]:
            conf_mem_set[conf][member['name']] = True

    retention_counts = {}
    for name in results.keys():
        for comp_name in results.keys():
            if name not in retention_counts:
                retention_counts[name] = {}
            retention_counts[name][comp_name] = 0

            for member in conf_mem_set[name].keys():
                retention_counts[name][comp_name] += 1 if member in conf_mem_set[comp_name] else 0

    # print table header
    print(f'conferences;{";".join(results.keys())}')
    for name in results.keys():
        print(f'{name};{";".join(str(n) for n in retention_counts[name].values())}')

def classify_aec_by_country(results):
    university_info = json.loads(download_file("https://github.com/Hipo/university-domains-list/raw/refs/heads/master/world_universities_and_domains.json"))
    university_info.extend([
        {'name': 'télécom sudparis', 'country': 'France'},
        {'name': 'ku leuven','country': 'Belgium'},
        {'name': 'imec-distrinet, ku leuven', 'country': 'Belgium'},
        {'name': 'university of crete', 'country': 'Greece'},
        {'name': 'ucla', 'country': 'United States'},
        {'name': 'tu munich', 'country': 'Germany'},
        {'name': 'inesc-id & ist u. lisboa in Portugal', 'country': 'Portugal'},
        {'name': 'ist lisbon & inesc-id', 'country': 'Portugal'},
        {'name': 'mpi-sws', 'country': 'Germany'},
        {'name': 'hkust', 'country': 'Hong Kong'},
        {'name': 'uc irvine', 'country': 'United States'},
        {'name': 'uiuc', 'country': 'United States'},
        {'name': 'school of computer science, university college dublin', 'country': 'Ireland'},
        {'name': 'imdea software institute', 'country': 'Spain'},
        {'name': 'university of chinese academy of sciences', 'country': 'China'},
        {'name': 'zhengqing', 'country': 'China'},
        {'name': 'the university of utah', 'country': 'United States'},
        {'name': 'institute of parallel and distributed systems, shanghai jiao tong university', 'country': 'China'},
        {'name': 'computing and imaging institute - the university of utah', 'country': 'United States'},
        {'name': 'university of crete & ics-forth', 'country': 'Greece'},
        {'name': 'ics-forth', 'country': 'Greece'},
        {'name': 'kaust', 'country': 'Saudi Arabia'},
        {'name': 'lrz', 'country': 'Germany'},
        {'name': 'ensta bretagne', 'country': 'France'},
        {'name': 'institute of computing technology chinese academy of sciences', 'country': 'China'},
        {'name': 'imdea networks institute & uc3m', 'country': 'Spain'},
        {'name': 'hasso plattner institute', 'country': 'Germany'},
        {'name': 'unist', 'country': 'South Korea'},
        {'name': 'niccolò cusano university', 'country': 'Italy'},
        {'name': 'uc irvine & mpi-sp', 'country': 'United States'},
        {'name': 'univ. toulouse iii, irit', 'country': 'France'},
        {'name': 'university of telepegaso,rome,italy', 'country': 'Italy'},
        {'name': 'leibniz supercomputing center', 'country': 'Germany'},
        {'name': 'inesc tec & u. minho', 'country': 'Portugal'},
        {'name': 'barkhausen institut', 'country': 'Germany'},
        {'name': 'the ohio state university', 'country': 'United States'},
    ])

    name_index = {}
    for uni in university_info:
        name_index[uni['name'].lower()] = uni
        splitted = uni['name'].split(" ")
        if len(splitted) > 1:
            for splitted_name in splitted:
                name_index[splitted_name.lower()] = uni
            if len(splitted) > 2:
                for s_cnt in range(1, len(splitted)-1):
                    name_index[" ".join(splitted[s_cnt:]).lower()] = uni


    prefix_tree = Trie(**name_index)
    per_year_country_stats = {}
    failed = []
    for conf, members in results.items():
        per_year_country_stats[conf] = {}
        for member in members:
            affiliation = member['affiliation'].lower()
            university = prefix_tree.values(prefix=affiliation)

            if university:
                university = university[0]
                #print(f'{affiliation} in {university["country"]} matched')
                per_year_country_stats[conf][university['country']] = per_year_country_stats[conf].get(university['country'], 0) + 1
            else:
                best_match = None
                best_match_ratio = 0
                for name in name_index.keys():
                    ratio = fuzz.ratio(name, affiliation)
                    if ratio > best_match_ratio:
                        best_match_ratio = ratio
                        best_match = name_index[name]

                if best_match_ratio > 80:
                    #print(f'{affiliation} in {best_match["country"]} with ratio {best_match_ratio}')
                    per_year_country_stats[conf][best_match['country']] = per_year_country_stats[conf].get(best_match['country'], 0) + 1
                else:
                    failed.append(affiliation)
                    print(f'Failed {affiliation} in {best_match["country"]} with ratio {best_match_ratio}')

    return per_year_country_stats, failed

def aec_by_country(results):
    per_year_country_stats, failed = classify_aec_by_country(results)

    # get all affiliations
    countries = set()
    for country_year in per_year_country_stats.values():
        for country in country_year.keys():
            countries.add(country)

    # print table header
    print(f'countries;{";".join(results.keys())};sum')
    for country in sorted(countries):
        print(f'{country};', end='')
        sum = 0
        for conf in per_year_country_stats.keys():
            print(f'{per_year_country_stats[conf].get(country, 0)}', end=';')
            sum += per_year_country_stats[conf].get(country, 0)
        print(f'{sum}')

    print(f'Number failed to identify {len(failed)}')
    print(f'List of failed affiliations:{", ".join(failed)}')

def main():
    parser = argparse.ArgumentParser(description='Scraping results of sys/secartifacts.github.io from conferences.')
    parser.add_argument('--conf_regex', type=str, default='.20[1|2][0-9]', help='Regular expression for conference name and or years')
    parser.add_argument('--prefix', type=str, default='sys', help='Prefix of artifacts website like sys for sysartifacts or sec for secartifacts')
    parser.add_argument('--analyze_affiliation',  action='store_true', help='Analyze affiliation of committee members')
    parser.add_argument('--analyze_affiliation_per_conference',  action='store_true', help='Analyze affiliation of committee members')
    parser.add_argument('--analyze_aec_retention',  action='store_true', help='Analyze if AEC members stay over multiple years or between conferences')
    parser.add_argument('--analyze_by_country',  action='store_true', help='Analyze from which countries AEC members are')

    args = parser.parse_args()

    results = get_committees(args.conf_regex, args.prefix)

    if args.analyze_affiliation:
        affiliation_stats = calculate_affiliation_stats(results)
        # print table header
        print("Affiliation; Count")
        for affiliation in sorted(affiliation_stats, key=lambda x: len(affiliation_stats[x]), reverse=True):
            print(f"{affiliation}; {len(affiliation_stats[affiliation])}")

    if args.analyze_affiliation_per_conference:
        affiliation_stats = calculate_affiliation_stats_per_year(results)
        # print table header
        print(f'Affiliation;{";".join(results.keys())};sum')

        for affiliation in sorted(affiliation_stats.items()):
            counts = []
            for conference in results.keys():
                if(conference in affiliation_stats[affiliation[0]]):
                    counts.append(len(affiliation_stats[affiliation[0]][conference]))
                else:
                    counts.append(0)
            print(f'{affiliation[0]};{";".join(str(i) for i in counts)};{sum(counts)}')

    if args.analyze_aec_retention:

        aec_retention(results)

    if args.analyze_by_country:

        aec_by_country(results)

if __name__ == "__main__":
    main()