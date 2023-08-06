#!/usr/bin/env python
from selenium import webdriver
import pandas as pd
import re
import time
from pathlib import Path


if __name__ == '__main__':
    driver = webdriver.Chrome()
    driver.implicitly_wait(5)
    driver.get("https://dc.healthinspections.us/?a=Inspections")
    search_button = driver.find_element(by="name", value="btnSearch")
    search_button.click()

    inspection_link_element_list = driver.\
        find_elements(by="xpath", value="//div[@id='divInspectionSearchResultsListing']/descendant::a")

    print("Found", len(inspection_link_element_list), "inspection links.")

    print("Extracting hrefs from links (this can take a while).")

    inspection_link_href_list = [x.get_attribute("href") for x in inspection_link_element_list]

    print("Extraction complete.")

    driver.quit()

    # Make a table of scraped data

    scraped_links_dataframe = pd.DataFrame({"link": inspection_link_href_list,
                                            "inspection_id": [int(re.search("(?<=inspectionID=)([0-9]+)", x).group())
                                                              for x in inspection_link_href_list],
                                            "data_extracted": False,
                                            "date_downloaded": time.strftime("%x")})

    if not Path("output/scraped_inspection_links.csv").exists():
        # If the saved table does not already exist, create it
        print("Saving data.")
        scraped_links_dataframe.to_csv("output/scraped_inspection_links.csv", index=False)
    else:
        # Merge and save the new frame
        existing_scraped_links_dataframe = pd.read_csv("output/scraped_inspection_links.csv")
        new_scraped_links_dataframe = scraped_links_dataframe.loc[~scraped_links_dataframe["inspection_id"].isin(
                 existing_scraped_links_dataframe["inspection_id"])]
        print("Compared with existing data - found", len(new_scraped_links_dataframe), "new links.")
        merged_scraped_links_dataframe = pd.concat([existing_scraped_links_dataframe, new_scraped_links_dataframe],
                                                   sort=True)
        merged_scraped_links_dataframe.to_csv("output/scraped_inspection_links.csv", index=False)
