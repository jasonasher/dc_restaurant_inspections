These scripts and data files are designed to scrape DC Department of Health restaurant inspection report data from https://dc.healthinspections.us/?a=Inspections

Here is the workflow that produces files in the `output` directory:

1) Run `01_scrape_inspection_links.py` to generate or update the `scraped_inspection_links.csv` file.
As this downloads the complete set of active links from the page above, processing this script can take a little while.
2) Run `02_extract_inspection_data.py` to process those links in the `scraped_inspection_links.csv` file that have not already had their data extracted.
This will generate a local cache of html files for each link, and either create or append the data to the `inspection_summary_data.csv` and `violation_details_data.csv` files.

Experimental alternative/additional steps:

2) Run `02alt_cache_potential_inspections.py` to sequentially scrape the range of known possible values of 'inspection_id' and generate a local cache of possible inspection reports.
This generates or updates the potential_inspection_ids.csv file. Note that some of these may not be valid reports (there are known broken duplicates on the server, for example).
3) Run `03alt_extract_potential_inspection_data.py` to process all such potential inspection reports (including those cached by #1 above) as in #2 above.
This will produce the `potential_inspection_summary_data.csv` and `potential_violation_details_data.csv` files.
The first of these has an additional column indicating if the given id is known to be valid (has been linked to by the dc.healthinspections.us site before, either in this scraping effort or in previous efforts).

Future versions of these scripts and data will resolve issues relating to duplicates and other invalid inspection reports.