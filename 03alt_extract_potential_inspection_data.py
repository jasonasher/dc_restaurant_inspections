#!/usr/bin/env python
from bs4 import BeautifulSoup
import datetime
import pandas as pd
import os
from pathlib import Path
from multiprocessing.pool import Pool
import pickle


def get_validity_data(inspection_id,
                      downloaded_cache_dir='scraped_inspections_html',
                      potential_downloaded_cache_dir='potential_inspections_html'):
    cache_path = downloaded_cache_dir + '/' + str(inspection_id)
    if os.path.exists(cache_path):
        cache_file_name = cache_path + '/inspection.html'
    else:
        cache_file_name = potential_downloaded_cache_dir + '/' + str(inspection_id) + '/inspection.html'
    soup = BeautifulSoup(open(cache_file_name), 'lxml')

    if not soup.find('span', string='Food Establishment Inspection Report'):
        print(str(inspection_id) + ' is cached but appears to be invalid')
        return

    def get_datetime_from_mdy_soup_array(mdy_soup_array):
        # First clean spaces
        cleaned_mdy_string_array = [x.text.split() for x in mdy_soup_array]
        if len(cleaned_mdy_string_array[0]) > 0:
            mdy_array = [int(x[0]) for x in cleaned_mdy_string_array]
            return datetime.date(month=mdy_array[0], day=mdy_array[1], year=mdy_array[2])
        else:
            return None

    def get_time_from_hm_soup_array(hm_soup_array):
        # First clean spaces
        clean_hm_string_array = [x.text.replace(u'\xa0', '') for x in hm_soup_array]
        if clean_hm_string_array[0] == '':
            return None
        else:
            return clean_hm_string_array[0] + ':' + clean_hm_string_array[1] + ' ' + clean_hm_string_array[2]

    # File Hash - Note: Not useful for duplicate detection because of individual file signing in hidden input divs
    # file_md5_hash = hashlib.md5(open(cache_file_name, 'rb').read()).hexdigest()

    # Establishment Name
    establishment_name_block = soup.find('span', string='Establishment Name').find_parent()
    establishment_name = ' '.join(establishment_name_block.contents[2].split())

    # Address
    address_block = soup.find('span', string='Address').find_parent()
    address = ' '.join(address_block.contents[2].split())
    city_state_zip_block = soup.find('span', string='City/State/Zip Code').find_parent()
    address = address + ' ' + ' '.join(city_state_zip_block.contents[2].split())

    # Telephone and E-mail
    telephone_email_block = soup.find('span', string='Telephone').find_parent()
    telephone = telephone_email_block.contents[3].text.replace(u'\xa0', '')
    email = next(iter(telephone_email_block.contents[6].split() or []), None)

    # Inspection Date and Time
    inspection_date_time_block = soup.find('span', string='Date of Inspection').find_parent()
    inspection_date = get_datetime_from_mdy_soup_array(inspection_date_time_block.contents[3:12:4])
    inspection_time_in = get_time_from_hm_soup_array(inspection_date_time_block.contents[x] for x in [15, 19, 21])
    inspection_time_out = get_time_from_hm_soup_array(inspection_date_time_block.contents[x] for x in [25, 29, 31])

    # License Holder
    license_holder_block = soup.find('span', string='License Holder').find_parent()
    license_holder = ' '.join(license_holder_block.contents[2].split())

    # License/Customer Number
    license_number_block = soup.find('span', string='License/Customer No.').find_parent()
    license_number = next(iter(license_number_block.contents[2].split() or []), None)

    # License Period
    license_period_block = soup.find('span', string='License Period').find_parent()
    license_period_start = get_datetime_from_mdy_soup_array(license_period_block.contents[3:12:4])
    license_period_end = get_datetime_from_mdy_soup_array(license_period_block.contents[15:24:4])

    # Inspection Type
    inspection_type = soup.find('span', string='\xa0Type of Inspection').find_next_sibling().get_text(strip=True)

    # Establishment Type
    establishment_type_block = soup.find('span', string='Establishment Type:').find_parent()
    establishment_type = ' '.join(establishment_type_block.contents[2].split())

    # Risk Category
    risk_category_red_square = soup.find('div', class_='checkboxRedN',
                                         attrs={'style': 'height:5px;width:5px;background-color:#FF0000;'})
    if risk_category_red_square is not None:
        risk_category = int(risk_category_red_square.find_previous_sibling().text[-1:])
    else:
        risk_category = None

    # Violation Counts
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
            return {'count': violations_row_elements_parsed[0],
                    'corrected_on_site': violations_row_elements_parsed[1],
                    'repeated': violations_row_elements_parsed[2]}
        else:
            return {'count': None,
                    'corrected_on_site': None,
                    'repeated': None}

    # Older inspection reports have 'Critical' and 'Noncritical' violations
    critical_violations_counts = extract_violation_counts(soup.find('b', string='Critical Violations'))
    noncritical_violations_counts = extract_violation_counts(soup.find('b', string='Noncritical Violations'))

    # Newer reports have 'Priority', 'Priority Foundation' and 'Core' violations
    priority_violations_counts = extract_violation_counts(soup.find('b', string='Priority'))
    priority_foundation_violations_counts = extract_violation_counts(soup.find('b', string='Priority Foundation'))
    core_violations_counts = extract_violation_counts(soup.find('b', string='Core'))

    # Violation Details
    violation_details_rows = list(soup.find('td', string='OBSERVATIONS').find_parent().next_siblings)[1:-2:2]

    def get_violation_description(violation_number):
        violation_number_td = soup.find('td', string = str(violation_number) + ".")
        if violation_number_td is not None:
            return violation_number_td.next_sibling.next_sibling.text
        else:
            return None

    def parse_violation_details_row(row):
        observation_tokens = row.td.contents[0].split()
        if len(observation_tokens) > 0:
            dcmr_25_code_block = row.td.find_next_sibling()
            if dcmr_25_code_block is not None:
                dcmr_25_code = dcmr_25_code_block.get_text(strip=True)
            else:
                dcmr_25_code = None
            try:
                int(observation_tokens[0][:-1])
                return {'inspection_id': inspection_id,
                        'violation_number': observation_tokens[0][:-1],
                        'violation_description': get_violation_description(observation_tokens[0][:-1]),
                        'violation_text': ' '.join(observation_tokens[2:]),
                        'dcmr_25_code': dcmr_25_code}
            except ValueError:
                return None
        else:
            return None

    violation_details = [x for x in
                         [parse_violation_details_row(row) for row in violation_details_rows] if x is not None]

    # Inspector Comments
    inspector_comments_block = soup.find('b', string='Inspector Comments:')
    inspector_comments = inspector_comments_block.find_parent().get_text(' ', strip=True)[20:]

    # Inspector Data (Name and Badge)
    inspector_data_block = soup.find('td', string='\xa0\xa0Inspector (Signature)').find_parent().find_previous_sibling()
    inspector_name = inspector_data_block.contents[3].text.replace(u'\xa0', '')
    inspector_badge_number = inspector_data_block.contents[5].text.replace(u'\xa0', '')

    return ({'inspection_summary':
             {'inspection_id': inspection_id,
              'establishment_name': establishment_name,
              'address': address,
              'telephone': telephone,
              'email': email,
              'inspection_date': inspection_date,
              'inspection_time_in': inspection_time_in,
              'inspection_time_out': inspection_time_out,
              'license_holder': license_holder,
              'license_number': license_number,
              'license_period_start': license_period_start,
              'license_period_end': license_period_end,
              'establishment_type': establishment_type,
              'risk_category': risk_category,
              'inspection_type': inspection_type,
              'total_violations': len(violation_details),
              'priority_violations': priority_violations_counts['count'],
              'priority_violations_corrected_on_site': priority_violations_counts['corrected_on_site'],
              'priority_violations_repeated': priority_violations_counts['repeated'],
              'priority_foundation_violations': priority_foundation_violations_counts['count'],
              'priority_foundation_violations_corrected_on_site':
                  priority_foundation_violations_counts['corrected_on_site'],
              'priority_foundation_violations_repeated': priority_foundation_violations_counts['repeated'],
              'core_violations': core_violations_counts['count'],
              'core_violations_corrected_on_site': core_violations_counts['corrected_on_site'],
              'core_violations_repeated': core_violations_counts['repeated'],
              'critical_violations': critical_violations_counts['count'],
              'critical_violations_corrected_on_site': critical_violations_counts['corrected_on_site'],
              'critical_violations_repeated': critical_violations_counts['repeated'],
              'noncritical_violations': noncritical_violations_counts['count'],
              'noncritical_violations_corrected_on_site': noncritical_violations_counts['corrected_on_site'],
              'noncritical_violations_repeated': noncritical_violations_counts['repeated'],
              'inspector_comments': inspector_comments,
              'inspector_name': inspector_name,
              'inspector_badge_number': inspector_badge_number},
             'violation_details': violation_details})


potential_inspection_ids_dataframe = pd.read_csv('output/potential_inspection_ids.csv')
scraped_inspection_links_dataframe = pd.read_csv('output/scraped_inspection_links.csv')

historical_known_valid_inspection_ids = pd.read_csv('historical_known_valid_inspection_ids.csv')['inspection_id']

chunk_size = 2000

ids_to_extract = potential_inspection_ids_dataframe[
                                   potential_inspection_ids_dataframe['was_live'] &
                                   ~potential_inspection_ids_dataframe['data_extracted']]['inspection_id']

if Path('output/potential_inspection_summary_data.csv').exists():
    potential_inspection_summary_data = pd.read_csv('output/potential_inspection_summary_data.csv')
    potential_violation_details_data = pd.read_csv('output/potential_violation_details_data.csv')
else:
    potential_inspection_summary_data = pd.DataFrame()
    potential_violation_details_data = pd.DataFrame()

if len(ids_to_extract) > 0:
    chunks = [ids_to_extract[x:x + chunk_size] for x in range(0, len(ids_to_extract), chunk_size)]
    pool = Pool(7)
    for i, chunk in enumerate(chunks):
        print("Processing chunk " + str(i+1) + " of " + str(len(chunks)))
        results = pool.map(get_validity_data, chunk)
        new_potential_inspection_summary_data = pd.concat([pd.DataFrame(x['inspection_summary'], index=[i])
                                                       for i, x in enumerate(results) if x is not None])
        potential_inspection_summary_data = pd.concat([potential_inspection_summary_data,
                                                       new_potential_inspection_summary_data])
        new_potential_violation_details_data = pd.concat([pd.DataFrame(x['violation_details'])
                                                      for x in results if x is not None])
        potential_violation_details_data = pd.concat([potential_violation_details_data,
                                                      new_potential_violation_details_data])

potential_inspection_summary_data = potential_inspection_summary_data[
    ['inspection_id',
     'establishment_name',
     'address',
     'telephone',
     'email',
     'inspection_date',
     'inspection_time_in',
     'inspection_time_out',
     'license_holder',
     'license_number',
     'license_period_start',
     'license_period_end',
     'establishment_type',
     'risk_category',
     'inspection_type',
     'total_violations',
     'priority_violations',
     'priority_violations_corrected_on_site',
     'priority_violations_repeated',
     'priority_foundation_violations',
     'priority_foundation_violations_corrected_on_site',
     'priority_foundation_violations_repeated',
     'core_violations',
     'core_violations_corrected_on_site',
     'core_violations_repeated',
     'critical_violations',
     'critical_violations_corrected_on_site',
     'critical_violations_repeated',
     'noncritical_violations',
     'noncritical_violations_corrected_on_site',
     'noncritical_violations_repeated',
     'inspector_comments',
     'inspector_name',
     'inspector_badge_number']]
potential_inspection_summary_data['known_valid'] = False
potential_inspection_summary_data.loc[
    potential_inspection_summary_data['inspection_id'].isin(
        scraped_inspection_links_dataframe['inspection_id']) |
    potential_inspection_summary_data['inspection_id'].isin(
        historical_known_valid_inspection_ids),
    'known_valid'] = True
potential_inspection_summary_data.to_csv('output/potential_inspection_summary_data.csv', index=False)

potential_violation_details_data = potential_violation_details_data[
    ['inspection_id', 'violation_number', 'violation_description', 'violation_text', 'dcmr_25_code']]
potential_violation_details_data.to_csv('output/potential_violation_details_data.csv', index=False)

# Update index
potential_inspection_ids_dataframe['data_extracted'] = True
potential_inspection_ids_dataframe.to_csv('output/potential_inspection_ids.csv', index=False)