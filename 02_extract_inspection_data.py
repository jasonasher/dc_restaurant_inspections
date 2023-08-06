#!/usr/bin/env python
import urllib3
from bs4 import BeautifulSoup
import re
import datetime
import pandas as pd
from pathlib import Path
import os
from multiprocessing.pool import Pool


# Function to scrape the inspection data from the specified url
# e.g. url = 'https://dc.healthinspections.us/webadmin/dhd_431/lib/mod/inspection/paper/'
#            '_paper_food_inspection_report.cfm?inspectionID=838175&wguid=1367&wgunm=sysact&wgdmn=431'
def scrape_inspection_data(url, verbose=False, downloaded_cache_dir="scraped_inspections_html"):
    # Inspection ID
    inspection_id = re.search("(?<=inspectionID=)([0-9]+)", url).group()

    http = urllib3.PoolManager()
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # We don't need to worry about https here

    # Save downloaded data to directory with inspection ID as the name
    cache_directory = downloaded_cache_dir + "/" + inspection_id
    if not os.path.exists(cache_directory):
        os.makedirs(cache_directory)
    cache_filename = cache_directory + "/inspection.html"

    if not Path(cache_filename).exists():
        # Need to download the file
        http = urllib3.PoolManager()
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # We don't need to worry about https here
        r = http.request('Get', url)
        cache_file = open(cache_filename, 'wb')
        cache_file.write(r.data)
        cache_file.close()
        soup = BeautifulSoup(r.data, 'lxml')
    else:
        # Load from cache
        cache_file = open(cache_filename)
        soup = BeautifulSoup(cache_file, 'lxml')

    # Establishment Name
    establishment_name_block = soup.find('span', string='Establishment Name').find_parent()
    establishment_name = " ".join(establishment_name_block.contents[2].split())
    # Alternative: establishment_name_block.get_text(' ', strip = True)[19:]

    # Inspection Date
    inspection_date_time_block = soup.find('span', string='Date of Inspection').find_parent()
    date_parts = [int(x.contents[0].split()[0]) for x in inspection_date_time_block.contents[3:14:4]]
    inspection_date = datetime.date(month=date_parts[0], day=date_parts[1], year=date_parts[2])

    # License Number
    license_number_block = soup.find('span', string='License/Customer No.').find_parent()
    license_number = next(iter(license_number_block.contents[2].split() or []), None)

    def extract_violation_counts(text_block):
        if text_block is not None:
            violations_block = text_block.find_parent().find_parent()
            violations_row_elements = violations_block.contents[3:14:4]

            def get_parsed_contents(x):
                split_contents = x.contents[0].split()
                if len(split_contents) > 0:
                    return int(split_contents[0])
                else:
                    return 0
            violations_row_elements_parsed = [get_parsed_contents(x) for x in violations_row_elements]
            return {"count": violations_row_elements_parsed[0],
                    "corrected_on_site": violations_row_elements_parsed[1],
                    "repeated": violations_row_elements_parsed[2]}
        else:
            return {"count": None,
                    "corrected_on_site": None,
                    "repeated": None}

    # Older inspection reports have 'Critical' and 'Noncritical' violations
    critical_violations_counts = extract_violation_counts(soup.find('b', string='Critical Violations'))
    noncritical_violations_counts = extract_violation_counts(soup.find('b', string='Noncritical Violations'))

    # Newer reports have 'Priority', 'Priority Foundation' and 'Core'
    priority_violations_counts = extract_violation_counts(soup.find('b', string='Priority'))
    priority_foundation_violations_counts = extract_violation_counts(soup.find('b', string='Priority Foundation'))
    core_violations_counts = extract_violation_counts(soup.find('b', string='Core'))

    # Violation Details
    violation_details_rows = list(soup.find('td', string='OBSERVATIONS').find_parent().next_siblings)[1:-2:2]

    def parse_violation_details_row(row):
        tokens = row.td.contents[0].split()
        if len(tokens) > 0:
            return [tokens[0][:-1], " ".join(tokens[2:])]
        else:
            return None

    violation_details = [x for x in
                         [parse_violation_details_row(row) for row in violation_details_rows] if x is not None]

    # Inspector Comments
    inspector_comments_block = soup.find('b', string="Inspector Comments:")
    inspector_comments = inspector_comments_block.find_parent().get_text(' ', strip=True)[20:]

    # Print Output
    if verbose:
        print("Finished parsing ", url)
        print("    inspection_id: ", inspection_id)
        print("    establishment_name: ", establishment_name)
        print("    inspection_date: ", inspection_date)
        print("    license_number: ", license_number)
        if priority_violations_counts["count"] is not None:
            print("    priority_violations:", priority_violations_counts)
            print("    priority_foundation_violations:", priority_foundation_violations_counts)
            print("    core_violations:", core_violations_counts)
        else:
            print("    critical_violations:", critical_violations_counts)
            print("    noncritical_violations:", noncritical_violations_counts)
        print("    violation_details_list:")
        for violation in violation_details:
            print("    ", violation)
        print("    inspector_comments: ", inspector_comments)

    inspection_summary = {"inspection_id": int(inspection_id),
                          "establishment_name": establishment_name,
                          "inspection_date": inspection_date,
                          "license_number": license_number,
                          "total_violations": len(violation_details),
                          "priority_violations": priority_violations_counts["count"],
                          "priority_violations_corrected_on_site": priority_violations_counts["corrected_on_site"],
                          "priority_violations_repeated": priority_violations_counts["repeated"],
                          "priority_foundation_violations": priority_foundation_violations_counts["count"],
                          "priority_foundation_violations_corrected_on_site":
                              priority_foundation_violations_counts["corrected_on_site"],
                          "priority_foundation_violations_repeated": priority_foundation_violations_counts["repeated"],
                          "core_violations": core_violations_counts["count"],
                          "core_violations_corrected_on_site": core_violations_counts["corrected_on_site"],
                          "core_violations_repeated": core_violations_counts["repeated"],
                          "critical_violations": critical_violations_counts["count"],
                          "critical_violations_corrected_on_site": critical_violations_counts["corrected_on_site"],
                          "critical_violations_repeated": critical_violations_counts["repeated"],
                          "noncritical_violations": noncritical_violations_counts["count"],
                          "noncritical_violations_corrected_on_site": noncritical_violations_counts["corrected_on_site"],
                          "noncritical_violations_repeated": noncritical_violations_counts["repeated"],
                          "inspector_comments": inspector_comments}
    return {"inspection_summary": inspection_summary,
            "violation_details": violation_details}


if __name__ == '__main__':
    scraped_links_dataframe = pd.read_csv("output/scraped_inspection_links.csv")
    urls_to_parse = scraped_links_dataframe[~scraped_links_dataframe["data_extracted"]]["link"]

    if len(urls_to_parse) > 0:
        results = Pool(20).map(scrape_inspection_data, urls_to_parse)

        inspection_summary_data = pd.concat(
            [pd.DataFrame(x["inspection_summary"], index=[i]) for i, x in enumerate(results)])
        inspection_summary_data = inspection_summary_data[["inspection_id",
                                                           "establishment_name",
                                                           "inspection_date",
                                                           "license_number",
                                                           "total_violations",
                                                           "priority_violations",
                                                           "priority_violations_corrected_on_site",
                                                           "priority_violations_repeated",
                                                           "priority_foundation_violations",
                                                           "priority_foundation_violations_corrected_on_site",
                                                           "priority_foundation_violations_repeated",
                                                           "core_violations",
                                                           "core_violations_corrected_on_site",
                                                           "core_violations_repeated",
                                                           "critical_violations",
                                                           "critical_violations_corrected_on_site",
                                                           "critical_violations_repeated",
                                                           "noncritical_violations",
                                                           "noncritical_violations_corrected_on_site",
                                                           "noncritical_violations_repeated",
                                                           "inspector_comments"]]


        def construct_details_frame_part(result_entry):
            frame_part = pd.DataFrame(result_entry["violation_details"], columns=["violation_number", "violation_text"])
            frame_part["inspection_id"] = result_entry["inspection_summary"]["inspection_id"]
            return frame_part


        violations_details_data = pd.concat([construct_details_frame_part(x) for x in results])
        violations_details_data = violations_details_data[["inspection_id", "violation_number", "violation_text"]]

        # Merge and save the new data
        def merge_and_save_new_data(data, filename):
            if not Path(filename).exists():
                print("Saving data.")
                # If the saved table does not already exist, create it
                data.to_csv(filename, index=False)
            else:
                print("Adding data.")
                # Merge and save the new frame
                existing_dataframe = pd.read_csv(filename)
                new_dataframe = data.loc[~data["inspection_id"].isin(
                    existing_dataframe["inspection_id"])]
                merged_dataframe = pd.concat(
                    [existing_dataframe, new_dataframe])
                merged_dataframe.to_csv(filename, index=False)


        print("Inspection summary data:")
        print(inspection_summary_data)
        merge_and_save_new_data(inspection_summary_data, "output/inspection_summary_data.csv")

        print("Violation details data:")
        print(violations_details_data)
        merge_and_save_new_data(violations_details_data, "output/violations_details_data.csv")

        # Update index
        scraped_links_dataframe.loc[~scraped_links_dataframe["data_extracted"], "data_extracted"] = True
        scraped_links_dataframe.to_csv("output/scraped_inspection_links.csv", index=False)

    else:
        print("All known links have already been processed")
