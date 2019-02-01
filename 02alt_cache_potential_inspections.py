#!/usr/bin/env python
import urllib3
import pandas as pd
import os
from multiprocessing.pool import Pool
import time


# This function will attempt to download the report with the specified inspection id from dc.healthinspections.us
# If the inspection has already been cached in the main download cache, it will be skipped
# If the server returns a web-page with nontrivial contents it will be cached (the server almost never gives 404 errors)
#
def cache_potential_inspection_data(inspection_id, verbose=False,
                                    downloaded_cache_dir="scraped_inspections_html",
                                    potential_downloaded_cache_dir="potential_inspections_html"):

    # First make sure this has not already been cached in the main directory
    if os.path.exists(downloaded_cache_dir + "/" + str(inspection_id)):
        if verbose:
            print(str(inspection_id) + " Already cached in main directory")
            return {"inspection_id": inspection_id, "was_live": True}

    # Otherwise, check to see if this has already been cached in the potential directory
    potential_cache_directory = potential_downloaded_cache_dir + "/" + str(inspection_id)
    if os.path.exists(potential_cache_directory):
        if verbose:
            print(str(inspection_id) + " Already cached in potential directory")
            return {"inspection_id": inspection_id, "was_live": True}

    # This has not been cached, so we will attempt to download it
    url = "https://dc.healthinspections.us/lib/mod/inspection/paper/" \
          "_paper_food_inspection_report.cfm?inspectionID=" + str(inspection_id) + "&wguid=1367&wgunm=sysact&wgdmn=431"
    http = urllib3.PoolManager()
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # We don't need to worry about https here
    r = http.request('Get', url)
    if verbose:
        print(str(inspection_id) + " " + str(r.data))
    if str(r.data) != "b''":
        try:
            os.makedirs(potential_cache_directory)
        except FileExistsError:
            pass
        potential_cache_filename = potential_cache_directory + "/inspection.html"
        potential_cache_file = open(potential_cache_filename, "wb")
        potential_cache_file.write(r.data)
        return {"inspection_id": inspection_id, "was_live": True}
    else:
        return {"inspection_id": inspection_id, "was_live": False}


scraped_links_dataframe = pd.read_csv("output/scraped_inspection_links.csv")
potential_inspection_ids_dataframe = pd.read_csv("output/potential_inspection_ids.csv")

max_known_id = max(scraped_links_dataframe["inspection_id"])
ids_to_cache = [x for x in range(1, max_known_id + 1) if x not in potential_inspection_ids_dataframe["inspection_id"]]

chunk_size = 2000

if len(ids_to_cache) > 0:
    chunks = [ids_to_cache[x:x + chunk_size] for x in range(0, len(ids_to_cache), chunk_size)]
    pool = Pool(40)
    for i, chunk in enumerate(chunks):
        print("Processing chunk " + str(i+1) + " of " + str(len(chunks)))
        results = pool.map(cache_potential_inspection_data, chunk)
        potential_new_inspection_ids_dataframe = pd.concat(
            [pd.DataFrame(x, index=[i]) for i, x in enumerate(results)])
        potential_new_inspection_ids_dataframe["date_downloaded"] = time.strftime("%x")
        potential_new_inspection_ids_dataframe["data_extracted"] = False
        potential_inspection_ids_dataframe = pd.concat([potential_inspection_ids_dataframe,
                                                        potential_new_inspection_ids_dataframe], sort=True)
        potential_inspection_ids_dataframe.to_csv("output/potential_inspection_ids.csv", index=False)
