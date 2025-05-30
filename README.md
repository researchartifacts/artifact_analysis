# Artifact Analysis Scripts

Analyzing artifact websites like sec/sysartifacts.github.io using simple python scripts.

### Artifact Results Scrapping

Returns a dictionary of conference name + year as the key and the artifacts entry yaml found in the results.md header. Prints the artifacts found per conference + year.

```
python sys-sec-artifacts-results-scrape.py
```

#### Arguments

*--conf_regex*

Regular expression to match the conference name assuming conference names have the format <name+year>. Default='.20[1|2][0-9]' Open Issue: Currently goes through all links in the page and as a result '.' matches every link.

*--prefix*

Select between sec or sysartifacts and possibly other artifact websites matching the same format. Default='sys'

### Testing repository and DOI existence

Downloads artifact results and URL info using the result scraping script and tests the existence of the repository or artifact URL. Keep in mind that Zenodo and similar services have rate limiting implemented and may fault.

```
python test_artifact_repositories.py
```

#### Arguments

*--conf_regex*

Regular expression to match the conference name assuming conference names have the format <name+year>. Default='.20[1|2][0-9]' Open Issue: Currently goes through all links in the page and as a result '.' matches every link.

*--prefix*

Select between sec or sysartifacts and possibly other artifact websites matching the same format. Default='sys'

*--url_key*

Selects which url_key to use in the artifacts results structure. 'artifact_url' or 'repository_url' are common values, but may differ by conference result page. Default: 'repository_url'

*--print_failed*

Prints failed entries at the end of the script.

### Collecting Statistics about Artifacts

Collect stars, forks, views, downloads, and last update date of artifacts depending on the artifact storage. Currently supported storages: Github, Zenodo, Figshare. If -1 or NA is printed, the view/download count or last date of update is not available.

```
python collect_artifact_stats.py
```

#### Arguments

*--conf_regex*

Regular expression to match the conference name assuming conference names have the format <name+year>. Default='.20[1|2][0-9]' Open Issue: Currently goes through all links in the page and as a result '.' matches every link.

*--prefix*

Select between sec or sysartifacts and possibly other artifact websites matching the same format. Default='sys'

*--url_key*

Selects which url_key to use in the artifacts results structure. 'artifact_url' or 'repository_url' are common values, but may differ by conference result page. Default: 'repository_url'

### Artifact Evaluation Committee Scrapping

Returns a dictionary of conference name + year as the key and the artifacts evaluation committee as a list of ```{'name': name, 'affiliation': affiliation}```. Prints the AEC members found per conference + year.

```
python sys-sec-committee-scrape.py
```

#### Arguments

*--conf_regex*

Regular expression to match the conference name assuming conference names have the format <name+year>. Default='.20[1|2][0-9]' Open Issue: Currently goes through all links in the page and as a result '.' matches every link.

*--prefix*

Select between sec or sysartifacts and possibly other artifact websites matching the same format. Default='sys'

*--print*

Print the list of each artifact evaluation committee per year.

### Artifact Evaluation Committee Statistics

Calculates various statistics about the AEC

```
python committee_statistics.py
```

#### Arguments

*--conf_regex*

Regular expression to match the conference name assuming conference names have the format <name+year>. Default='.20[1|2][0-9]' Open Issue: Currently goes through all links in the page and as a result '.' matches every link.

*--prefix*

Select between sec or sysartifacts and possibly other artifact websites matching the same format. Default='sys'

*--analyze_affiliation*

Calculates how many times members of an affiliation have participated in matching conferences and prints a sorted list of counts.

*--analyze_affiliation_per_conference*

Calculates how many times members of an affiliation have participated in matching conferences and prints the number for each matching conference.

*--analyze_aec_retention*

Analyzes the similarity of AEC members across pairs of matching conferences and prints a table with each pairs count.

*--analyze_by_country*

Analyzes the country location of each AEC member and prints the number of involved AEC members per country for each matching conference