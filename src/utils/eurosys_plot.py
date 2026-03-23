import argparse
import json
import matplotlib.pyplot as plt
import os
import shutil
from sys_sec_committee_scrape import get_committees
from committee_statistics import classify_aec_by_country
from sys_sec_artifacts_results_scrape import get_ae_results
from collect_artifact_stats import get_all_artifact_stats
from test_artifact_repositories import check_artifact_exists
from pycountry_convert import country_name_to_country_alpha2, country_alpha2_to_continent_code

# eurosys 2021-2025 data
eurosys_data = {
    'Years': [2021.0, 2022.0, 2023.0, 2024.0, 2025.0],
    'AEC size': [50, 65, 64, 49, 93],
    'AE submissions': [22, 33, 32, 33, 45],
    'Spring sub': [None, None, 15, 23, 15],
    'Fall sub': [None, None, 17, 10, 30],
    'Accepted Papers': [38, 45, 54, 71, 85],
    '% submitted': [57.9, 73.3, 59.3, 46.5, 52.9],
    'Artifact Available': [21, 33, 31, 32, 44],
    '% available sub': [95.5, 100.0, 96.9, 97.0, 97.8],
    '% available pap': [55.3, 73.3, 57.4, 45.1, 51.8],
    'available acceptance rate': [100, 100, 100, 100, 100],
    'Artifact Functional': [18, 27, 24, 25, 42],
    '% functional sub': [82, 82, 75, 76, 93],
    '% functional pap': [47.4, 60.0, 44.4, 35.2, 49.4],
    'functional acceptance rate': [90, 96, 80, 90, 98],
    'Results Reproduced': [14, 20, 8, 12, 21],
    '% reproduced sub': [63.6, 60.6, 25.0, 36.4, 46.7],
    '% reproduced pap': [36.8, 44.4, 14.8, 16.9, 24.7],
    'Rep acceptance rate': [74, 77, 40, 72, 75],
}

def number_papers_artifacts():
    # number of papers and artifacts
    number_artiact_papers = plt.figure(3)
    plt.plot(eurosys_data['Years'], eurosys_data['AE submissions'], linewidth=2, label="Artifact submissions")
    plt.plot(eurosys_data['Years'], eurosys_data['Accepted Papers'], linewidth=2, label="Accepted papers")
    plt.legend(loc='lower right')
    plt.xlabel('Year')
    plt.ylabel('Number of artifacts or accepted papers')
    plt.axis([2020.5, 2025.5,0, max(eurosys_data['Accepted Papers'])+10])
    plt.xticks(range(int(eurosys_data['Years'][0]), int(eurosys_data['Years'][-1])+1, 1))
    number_artiact_papers.savefig('figures/eurosys_artifact_papers.pdf', bbox_inches='tight')

def percent_submitted():
    # create percent submitted figure
    percent_submitted_f = plt.figure(1)
    plt.plot(eurosys_data['Years'], eurosys_data['% submitted'], linewidth=2)
    plt.xlabel('Year')
    plt.ylabel('Accepted papers submitting artifacts in %')
    plt.axis([2020.5, 2025.5, 0, 101])
    plt.xticks(range(int(eurosys_data['Years'][0]), int(eurosys_data['Years'][-1])+1, 1))
    percent_submitted_f.savefig('figures/eurosys_percent_submitted.pdf', bbox_inches='tight')

def combined_number_papers_artifacts_percent_submitted():
    # Combined figure with two y-axes
    combined_figure = plt.figure(9)
    ax1 = combined_figure.add_subplot(111)

    # Plot absolute numbers on the left y-axis
    lns1 = ax1.plot(eurosys_data['Years'], eurosys_data['AE submissions'], linewidth=2, label="Artifact submissions")
    lns2 = ax1.plot(eurosys_data['Years'], eurosys_data['Accepted Papers'], linewidth=2, label="Accepted papers")
    ax1.set_xlabel('Year')
    ax1.set_ylabel('Number of artifacts or accepted papers')
    #ax1.legend(loc='upper left')

    # Create a second y-axis for percentages
    ax2 = ax1.twinx()
    lns3 = ax2.plot(eurosys_data['Years'], eurosys_data['% submitted'], linewidth=2, label="% Submitted", color='green', linestyle='--')
    ax2.set_ylabel('Accepted papers submitting artifacts in %')
    ax2.axis([2020.5, 2025.5, 0, 101])
    #ax2.legend(loc='lower right')
    lns = lns1+lns2+lns3
    labs = [l.get_label() for l in lns]
    ax1.legend(lns, labs, loc='upper left')

    # Save the figure
    combined_figure.savefig('figures/eurosys_combined_papers_artifacts_percent.pdf', bbox_inches='tight')

def badge_acceptance_rates():
    # badge acceptance rates
    badge_acceptance_rates = plt.figure(2)
    plt.plot(eurosys_data['Years'], eurosys_data['available acceptance rate'], linewidth=2, label="Available badge")
    plt.plot(eurosys_data['Years'], eurosys_data['functional acceptance rate'], linewidth=2, label="Functional badge")
    plt.plot(eurosys_data['Years'], eurosys_data['Rep acceptance rate'], linewidth=2, label="Results Reproduced badge")
    plt.legend(loc='lower right')
    plt.xlabel('Year')
    plt.ylabel('Badge acceptance rate in %')
    plt.axis([2020.5, 2025.5, 0, 101])
    plt.xticks(range(int(eurosys_data['Years'][0]), int(eurosys_data['Years'][-1])+1, 1))
    badge_acceptance_rates.savefig('figures/eurosys_badge_acceptance_rates.pdf', bbox_inches='tight')

def aec_badges_per_paper():
    # badges per paper
    badge_acceptance_rates = plt.figure(4)
    plt.plot(eurosys_data['Years'], eurosys_data['% available pap'], linewidth=2, label="Available badge")
    plt.plot(eurosys_data['Years'], eurosys_data['% functional pap'], linewidth=2, label="Functional badge")
    plt.plot(eurosys_data['Years'], eurosys_data['% reproduced pap'], linewidth=2, label="Results Reproduced badge")
    plt.legend(loc='upper right')
    plt.xlabel('Year')
    plt.ylabel('% of papers with badge')
    plt.axis([2020.5, 2025.5, 0, 101])
    plt.xticks(range(int(eurosys_data['Years'][0]), int(eurosys_data['Years'][-1])+1, 1))
    badge_acceptance_rates.savefig('figures/eurosys_badge_percent_paper.pdf', bbox_inches='tight')

def extract_aec_countries():
    if os.path.exists('cache/aec_by_country.json') and os.path.exists('cache/sorted_countries.json'):
        with open('cache/aec_by_country.json', 'r') as f, open('cache/sorted_countries.json', 'r') as s:
            return json.load(s), json.load(f)
    # committee location
    eurosys_aec = get_committees('eurosys20', 'sys')
    aec_by_country, failed = classify_aec_by_country(eurosys_aec)
    print(f'Number failed to identify {len(failed)}')
    with open('cache/aec_by_country.json', 'w') as f:
        json.dump(aec_by_country, f)

    countries = {}
    for country_year in aec_by_country.values():
        for country in country_year.keys():
            if country not in countries:
                countries[country] = 0

            countries[country] += country_year[country]

    sorted_countries = sorted(countries.items(), key=lambda x: x[1], reverse=True)

    with open('cache/sorted_countries.json', 'w') as f:
        json.dump(sorted_countries, f, indent=4)
    return sorted_countries, aec_by_country

def aec_country():
    sorted_countries, _ = extract_aec_countries()

    aec_by_country_f = plt.figure(5)
    plt.bar([x[0] for x in sorted_countries[:10]], [x[1] for x in sorted_countries[:10]])
    plt.xticks(rotation=45, ha='right')
    plt.xlabel('Country')
    plt.ylabel('Number of AEC members')
    aec_by_country_f.savefig('figures/eurosys_aec_by_country.pdf', bbox_inches='tight')

def aec_country_by_year():
    sorted_countries, aec_by_country = extract_aec_countries()

    # committee location by year for top 15
    aec_by_country_year = {}
    for top_country, sum in sorted_countries[:10]:
        aec_by_country_year[top_country] = []
        for year, country_year in aec_by_country.items():
            if top_country in country_year:
                aec_by_country_year[top_country].append(country_year[top_country])
            else:
                aec_by_country_year[top_country].append(0)

    aec_by_country_f = plt.figure(6)
    for country, number_per_year in aec_by_country_year.items():
        plt.plot(eurosys_data['Years'], number_per_year, linewidth=1, label=country)
    plt.xlabel('Year')
    plt.ylabel('Number of AEC members')
    plt.xticks(range(int(eurosys_data['Years'][0]), int(eurosys_data['Years'][-1])+1, 1))
    plt.legend(loc='upper right')
    aec_by_country_f.savefig(f'figures/eurosys_aec_by_country_per_year.pdf', bbox_inches='tight')

def aec_continents():
    sorted_countries, aec_by_country = extract_aec_countries()

    continent_map = {
        'AF': 'Africa',
        'AS': 'Asia',
        'EU': 'Europe',
        'NA': 'North America',
        'SA': 'South America',
        'OC': 'Oceania',
        'AN': 'Antarctica'
    }

    continent_counts = {}

    for country, count in sorted_countries:
        try:
            alpha2 = country_name_to_country_alpha2(country)
            continent_code = country_alpha2_to_continent_code(alpha2)
            continent = continent_map[continent_code]
            if continent not in continent_counts:
                continent_counts[continent] = 0
            continent_counts[continent] += count
        except KeyError:
            print(f"Could not map country {country} to a continent.")

    aec_by_continent_f = plt.figure(7)
    plt.bar(continent_counts.keys(), continent_counts.values())
    plt.xticks(rotation=45, ha='right')
    plt.xlabel('Continent')
    plt.ylabel('Number of AEC members')
    aec_by_continent_f.savefig('figures/eurosys_aec_by_continent.pdf', bbox_inches='tight')

def aec_continents_by_year():
    _, aec_by_country = extract_aec_countries()

    continent_map = {
        'AF': 'Africa',
        'AS': 'Asia',
        'EU': 'Europe',
        'NA': 'North America',
        'SA': 'South America',
        'OC': 'Oceania'
    }

    continent_counts_by_year = {continent: [0] * len(eurosys_data['Years']) for continent in continent_map.values()}

    for year_idx, year in enumerate(eurosys_data['Years']):
        for country, count in aec_by_country.get(f'eurosys{int(year)}', {}).items():
            try:
                alpha2 = country_name_to_country_alpha2(country)
                continent_code = country_alpha2_to_continent_code(alpha2)
                continent = continent_map[continent_code]
                continent_counts_by_year[continent][year_idx] += count
            except KeyError:
                print(f"Could not map country {country} to a continent.")

    aec_by_continent_year_f = plt.figure(8)
    for continent, counts in continent_counts_by_year.items():
        plt.plot(eurosys_data['Years'], counts, linewidth=2, label=continent)
    plt.xlabel('Year')
    plt.ylabel('Number of AEC members')
    plt.xticks(range(int(eurosys_data['Years'][0]), int(eurosys_data['Years'][-1]) + 1, 1))
    plt.legend(loc='upper left')
    aec_by_continent_year_f.savefig('figures/eurosys_aec_by_continent_per_year.pdf', bbox_inches='tight')

def get_artifact_stats():
    # cdf for stars/forks/view/downloads of artifacts
    if os.path.exists('cache/ae_stats.json'):
        with open('cache/ae_stats.json', 'r') as f:
            ae_results = json.load(f)
    else:
        url_keys = ['repository_url', 'artifact_url']
        ae_results = get_ae_results('eurosys202[1-5]', 'sys')
        ae_results, _, _ = check_artifact_exists(ae_results, url_keys)
        ae_results = get_all_artifact_stats(ae_results, url_keys)
        with open('cache/ae_stats.json', 'w') as f:
            json.dump(ae_results, f, indent=4)

    if os.path.exists('cache/stars.json') and os.path.exists('cache/forks.json') and os.path.exists('cache/views.json') and os.path.exists('cache/downloads.json'):
        stars = json.load(open('cache/stars.json'))
        forks = json.load(open('cache/forks.json'))
        views = json.load(open('cache/views.json'))
        downloads = json.load(open('cache/downloads.json'))
    else:
        stars = {}
        forks = {}
        views = {}
        downloads = {}

        for year, per_year_ae_results in ae_results.items():
            stars[year] = []
            forks[year] = []
            views[year] = []
            downloads[year] = []
           # print(year)
           # print(per_year_ae_results)
            for ae_result in per_year_ae_results:
                if 'stats' in ae_result:
                    if 'github_stars' in ae_result['stats']:
                        stars[year].append(ae_result['stats']['github_stars'])
                    if 'github_forks' in ae_result['stats']:
                        forks[year].append(ae_result['stats']['github_forks'])
                    if 'zenodo_views' in ae_result['stats']:
                        views[year].append(ae_result['stats']['zenodo_views'])
                    if 'zenodo_downloads' in ae_result['stats']:
                        downloads[year].append(ae_result['stats']['zenodo_downloads'])
                    if 'figshare_views' in ae_result['stats']:
                        views[year].append(ae_result['stats']['figshare_views'])
                    if 'figshare_downloads' in ae_result['stats']:
                        downloads[year].append(ae_result['stats']['figshare_downloads'])

            # remove empty years
            if len(stars[year]) == 0:
                del stars[year]
            if len(forks[year]) == 0:
                del forks[year]
            if len(views[year]) == 0:
                del views[year]
            if len(downloads[year]) == 0:
                del downloads[year]

        with open('cache/stars.json', 'w') as s, \
            open('cache/forks.json', 'w') as f, \
            open('cache/views.json', 'w') as v,\
            open('cache/downloads.json', 'w') as d:
            json.dump(stars, s)
            json.dump(forks, f)
            json.dump(views, v)
            json.dump(downloads, d)

    return stars, forks, views, downloads

def plot_cdf_artifact_stat(stats, metrics):
    f = plt.figure()
    ax  = f.add_subplot()
    for metric in metrics:
        for year, values in stats[metric].items():
            ax.ecdf(values, label=f'{metric} {year[7:]}', linewidth=1)
    plt.legend(loc='lower right')
    plt.xlabel(f'Number of {"/".join(metrics)} of artifacts')
    plt.ylabel('CDF')
    f.savefig(f'figures/eurosys_cdf_artifact_{"_".join(metrics)}.pdf', bbox_inches='tight')

def cdf_artifact_stats():
    stars, forks, views, downloads = get_artifact_stats()
    stats = {'stars': stars, 'forks': forks, 'views': views, 'downloads': downloads}

    # cdf for stars/forks/view/downloads of artifacts
    plot_cdf_artifact_stat(stats, ['stars', 'forks', 'views', 'downloads'])

    plot_cdf_artifact_stat(stats, ['stars'])
    plot_cdf_artifact_stat(stats, ['forks'])
    plot_cdf_artifact_stat(stats, ['stars', 'forks'])
    plot_cdf_artifact_stat(stats, ['views'])
    plot_cdf_artifact_stat(stats, ['downloads'])


def main():
    # Create 'figures' folder if it doesn't exist
    os.makedirs('figures', exist_ok=True)
    os.makedirs('cache', exist_ok=True)

    plt.rc('font', size=12)

    parser = argparse.ArgumentParser(description='Plotting figures for EuroSys')
    parser.add_argument('--plot_all', action='store_true', help='Plot all figures')
    parser.add_argument('--plot_number_papers_artifacts', action='store_true', help='Plot number of papers and artifacts')
    parser.add_argument('--plot_percent_submitted', action='store_true', help='Plot percent submitted')
    parser.add_argument('--plot_combined', action='store_true', help='Plot combined number of papers, artifacts, and percent submitted')
    parser.add_argument('--plot_badge_acceptance_rates', action='store_true', help='Plot badge acceptance rates')
    parser.add_argument('--plot_aec_badges_per_paper', action='store_true', help='Plot badges per paper')
    parser.add_argument('--plot_aec_country', action='store_true', help='Plot committee location')
    parser.add_argument('--plot_aec_country_by_year', action='store_true', help='Plot committee location by year')
    parser.add_argument('--plot_cdf_artifact_stats', action='store_true', help='Plot cdf for stars/forks/view/downloads of artifacts')
    parser.add_argument('--plot_aec_continents', action='store_true', help='Plot AEC members by continent')
    parser.add_argument('--plot_aec_continents_by_year', action='store_true', help='Plot AEC members by continent over the years')
    parser.add_argument('--delete_cache', action='store_true', help='Delete json cache files')
    args = parser.parse_args()

    if args.plot_number_papers_artifacts or args.plot_all:
        number_papers_artifacts()
    if args.plot_percent_submitted or args.plot_all:
        percent_submitted()
    if args.plot_combined:
        combined_number_papers_artifacts_percent_submitted()
    if args.plot_badge_acceptance_rates or args.plot_all:
        badge_acceptance_rates()
    if args.plot_aec_badges_per_paper or args.plot_all:
        aec_badges_per_paper()
    if args.plot_aec_country or args.plot_all:
        aec_country()
    if args.plot_aec_country_by_year or args.plot_all:
        aec_country_by_year()
    if args.plot_cdf_artifact_stats or args.plot_all:
        cdf_artifact_stats()
    if args.plot_aec_continents or args.plot_all:
        aec_continents()
    if args.plot_aec_continents_by_year or args.plot_all:
        aec_continents_by_year()
    if args.delete_cache:
        try:
            shutil.rmtree('cache/')
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()