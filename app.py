# -*- coding: utf-8 -*-
"""
Created on Mon May  8 13:00:52 2023

@author: regru
"""

import os
import json
import numpy as np
import pandas as pd
import time
import spacy
import openai
import glob
import re
import pytesseract
from pdf2image import convert_from_path
import PyPDF2
import io
from PyPDF2 import PdfReader
from IPython.display import display
import streamlit as st

##############################
# Funtions
def extract_mm_dd_yyyy(text):
    # extracts date in the format mm/dd/yyyy from the format '{dd}th day of {Month}, yyyy' or 'mm/dd/yyyy
    # First 1 or 2 digits must be day, last 4 digits must be year
    # Patterns
    months = {'January':1,'February':2,'March':3,'April':4,'May':5,'June':6,'July':7,'August':8,'September':9,'October':10,'November':11,'December':12}    
    month_pattern = '|'.join(months.keys())
    yyyy_pattern = re.compile(r'\d{4}')
    dd_pattern = re.compile(r'\d{1,2}')
    # Matches
    string = text.strip()
    # If date contains '/' assume mm/dd/yyyy
    if bool(re.search('/', string)):
        final_date = string.split()[0]
    else:
        yyyy = yyyy_pattern.findall(string)[0]
        dd = dd_pattern.findall(string.split(yyyy)[0])[0]
        mm = months[re.search(month_pattern, string, re.IGNORECASE).group(0)]
        if yyyy.isdigit():
            final_date = f'{mm}/{dd}/{yyyy}'
        else:
            final_date = 'Error: Improperly formatted text'
    return final_date

# https://streamlit.io/gallery
# Find emojis here: https://www.webfx.com/tools/emoji-cheat-sheet/
def main():
    st.set_page_config(page_title="CTA Data Extraction")
    st.header("Extract Data From Your Contracts")
    pdf_files = st.file_uploader("Upload Files", accept_multiple_files=True, type="pdf")
    # Extract Data
    if bool(pdf_files):
        st.header('Extracted Data')
        ##############################################################################
        # files_root = r'C:\Users\regru\Desktop\PDF_OCR\NegotiationAI_Example_Data\ACTA_Contracts'
        # pdf_files = glob.glob(f'{files_root}\\*.pdf')
    
        # Regex compiled patters
        first_para_pattern = re.compile(r'.*?Whereas',re.IGNORECASE)
        def_term_pattern = re.compile(r'\(.{,30}\)',re.IGNORECASE)
        eff_date_format = re.compile(r'(\(the.{,3}Effective Date.{,3}\)|\(.{,3}Effective Date.{,3}\))',re.IGNORECASE)
        eff_date_pattern1 = re.compile(r'(\d{1,2}.{,4}day\s*of.{,11}, \d{4}.{,3}\(.{,10}Effective Date.{,3}\)|\d{1,2} [a-zA-Z]{,10} \d{4}.{,3}\(.{,10}Effective Date.{,3}\)|[a-zA-Z]{,10} \d{1,2},.{,3}\d{4}.{,3}\(.{,10}Effective Date.{,3}\))',re.IGNORECASE)
        eff_date_pattern2 = re.compile(r'date.{,15}last signature.{,20}\(.{,10}Effective Date.{,5}\)',re.IGNORECASE)
        eff_date_pattern3 = re.compile(r'Effective Date.{,15}date.{,15}last signatur',re.IGNORECASE)
        institution_pattern = re.compile(r'\).*?\(.{,20}Institution.{,5}\)',re.IGNORECASE)
        sponsor_pattern = re.compile(r'\).*?\(.{,20}Sponsor.{,5}\)',re.IGNORECASE)
        pi_pattern = re.compile(r'\)?.*?\(.{,20}Principal Investigator.{,5}\)',re.IGNORECASE)
        section_pattern = re.compile(r'(\n?(?<!\d)(?<!\.)\d+\.(?!\d).+\n+|^(?<!\d)(?<!\.)\d+\.(?!\d).+\n+)') # Pattern must be digit then '.' any text then ends with one or more '\n'
        roman_numeral_section_pattern = re.compile(r'(\nI{1,3}\.\s+.*?\n|\nIV\.\s+.*?\n|\nVI{0,3}\.\s+.*?\n|\nIX\.\s+.*?\n|\nXI{0,3}\.\s+.*?\n|\nXIV\.\s+.*?\n|\nXVI{0,3}\.\s+.*?\n|\nXIX\.\s+.*?\n|\nXX\.\s+.*?\n)')
        tin_pattern = re.compile(r'tax identification number is.{,2}\s?\d{2}-\d{7}',re.IGNORECASE)
        recitals_pattern = re.compile(r'whereas\s*,\s*[a-zA-Z0-9,]+[^?!.;]*',re.IGNORECASE)
        study_drug_text_pattern = re.compile(r'\.[a-zA-Z0-9,\s\-]+\(.{,5}Study Drug.{,5}\)',re.IGNORECASE)
        inventions_pattern = re.compile(r'\.[a-zA-Z0-9,;\s\-]+\(.{,2}Inventions.{,2}\)[a-zA-Z0-9,;\s\-]+\.',re.IGNORECASE)
    
        # Spacy Model
        nlp = spacy.load("en_core_web_sm")
        ent_patterns = [{'label':'Def_Term','pattern':'Sponsor'},
                    {'label':'Def_Term','pattern':'Institution'},
                    {'label':'Def_Term','pattern':'Principal Investigator'},
                    {'label':'Def_Term','pattern':'Budget'},
                    {'label':'Def_Term','pattern':'Equipment'},
                    {'label':'Def_Term','pattern':'Inventions'}
                    ]
        ruler = nlp.add_pipe("entity_ruler", before='ner')
        ruler.add_patterns(ent_patterns)
    
        ##############################################################################
        unread_files = []
        extracted_data = []
        # Read-in files, extract data
        for fn in pdf_files:
            # File to read
            # file_name = fn.split('\\')[-1]
            # nlp.analyze_pipes()
            try:
                ##################
                # Read PDF
                reader = PdfReader(fn)
                temp_doc = {}
                raw_doc0 = []  
                for i,text in enumerate(reader.pages):
                    page = reader.pages[i] #read text on each page
                    # insert page number and text into dictionary
                    temp_doc[f'pg{i+1}'] = page.extract_text()
                # Join text into one document
                for pg_text in temp_doc.values():
                    raw_doc0.append(pg_text)
                raw_doc = ' '.join(raw_doc0) #join pages from list into one document
                clean_doc = raw_doc.replace('\n','').strip()
            # st.write(fn.name)
            ##############################################################################
                # Extract 1st paragraph
                first_para_match = first_para_pattern.findall(temp_doc['pg1'].replace('\n','').strip())[0]
                first_pg = temp_doc['pg1'].replace('\n','').strip()
                sponsor_text = first_para_match
                institution_text = first_para_match
                # Identify location of Sponsor and Institution
                first_para_sponsor_bool = False
                first_pg_sponsor_bool = False
                try:
                    sponsor_text_match = sponsor_pattern.findall(first_para_match)[0]
                    first_para_sponsor_bool = True
                except:
                    try:
                        sponsor_text_match = sponsor_pattern.findall(first_pg)[0]
                        first_pg_sponsor_bool = True
                        sponsor_text = first_pg
                    except:
                        pass
                # Institution Location
                first_para_institution_bool = False
                first_pg_institution_bool = False
                try:
                    institution_text_match = institution_pattern.findall(first_para_match)[0]
                    first_para_institution_bool = True
                except:
                    try:
                        institution_text_match = institution_pattern.findall(first_pg)[0]
                        first_pg_institution_bool = True
                        institution_text = first_pg
                    except:
                        pass
                  
            ##############################################################################
                # Identify if ("Sponsor/Institution") has been replaced by ("Sponsor Name/Institution Name")
                # Is the Defined Word ("Sponsor") missing from first page of text
                sponsor_missing_bool = False
                institution_missing_bool = False
                if (first_para_sponsor_bool == False) and (first_pg_sponsor_bool == False):
                    sponsor_missing_bool = True
                # Is the Defined Word ("Institution") missing from first page of text
                if (first_para_institution_bool == False) and (first_pg_institution_bool == False):
                    institution_missing_bool = True
                # If either/or both Defined words are missing, then search for name like ("Aastrom")
                missing_def_term_sponsor_bool = False
                missing_def_term_institution_bool = False
                if (sponsor_missing_bool == True) | (institution_missing_bool == True):          
                    def_term_match = def_term_pattern.findall(first_para_match)
                    # Clean found Defined Terms
                    clean_def_terms = []
                    for text in def_term_match:
                        clean_def_terms.append(re.sub("[^a-zA-Z]", " ",text).replace('the','').replace('hereinafter','').lower().strip())
                    # Expected Defined Terms 
                    expected_1st_para_def_terms = set(['sponsor','effective date','institution','agreement'])
                    # Identify missing defined term
                    if 'sponsor' not in list(expected_1st_para_def_terms.intersection(set(clean_def_terms))):
                        missing_def_term_sponsor_bool = True
                    if 'institution' not in list(expected_1st_para_def_terms.intersection(set(clean_def_terms))):
                        missing_def_term_institution_bool = True
                    # Set missing Defined Term
                    if bool(list(set(clean_def_terms) - expected_1st_para_def_terms)):
                        missing_def_term = list(set(clean_def_terms) - expected_1st_para_def_terms)[0]
                
            ##############################################################################
                ######################## Effective Date #############################
                eff_date_format_matches = eff_date_format.findall(first_para_match)
                # Determine format of Effective Date
                if bool(eff_date_format_matches):
                    try:          
                        eff_date_contract_format = eff_date_pattern1.findall(first_para_match)[0]
                        # Call Function "extract_mm_dd_yyyy" to extract 'mm/dd/yyyy'
                        effective_date = extract_mm_dd_yyyy(eff_date_contract_format)
                    except:            
                        try:
                            empty = eff_date_pattern2.findall(first_para_match)[0]
                            effective_date = 'Date of the last signature'
                        except:
                            effective_date = 'Not Found'
                else:
                    try:
                        empty = eff_date_pattern3.findall(first_para_match)[0]
                        effective_date = 'Date of the last signature'
                    except:
                        effective_date = 'Not Found'
            ##############################################################################
                # Sponsor - Name
                sponsor = []
                # If ("Sponsor") is not found then use ("{sponsor name}") to find sponsor
                if missing_def_term_sponsor_bool:
                    sponsor_pattern = re.compile(fr'\).*?\(.{{,20}}{missing_def_term}.{{,5}}\)',re.IGNORECASE)
                    try:
                        sponsor_text_match = sponsor_pattern.findall(sponsor_text)[0]
                        # Open small Spacy model
                        sponsor_doc = nlp(sponsor_text_match)
                        # Extract Entities
                        for ent in sponsor_doc.ents:
                            if missing_def_term in ent.text.lower():
                                sponsor = ent.text
                        if not bool(sponsor):
                            sponsor = 'Not found'
                    except:
                        sponsor = 'Not found'
                    sponsor_pattern = re.compile(r'\).*?\(.{,20}Sponsor.{,5}\)',re.IGNORECASE)
                else:
                    try:
                        sponsor_text_match = sponsor_pattern.findall(sponsor_text)[0]
                        # Open small Spacy model
                        sponsor_doc = nlp(sponsor_text_match)
                        # Extract Entities
                        for ent in sponsor_doc.ents:
                            if ent.label_ == 'ORG' and not bool(re.findall(r'[0-9]+',ent.text)) and not bool(re.findall(r'(Office|Division|Branch|Function|Subsidiary)',ent.text)):
                                sponsor = ent.text
                        if not bool(sponsor):
                            sponsor = 'Not found'
                    except:
                        sponsor = 'Not found'
                ########################
                institution = []
                # If ("Institution") is not found then use ("{institution namd}") to find institution
                if missing_def_term_institution_bool:
                    institution_pattern = re.compile(fr'\).*?\(.{{,20}}{missing_def_term}.{{,5}}\)',re.IGNORECASE)
                    try:
                        institution_text_match = institution_pattern.findall(institution_text)[0]
                        # Open small Spacy model
                        institution_doc = nlp(institution_text_match)
                        # Extract Entities
                        for ent in institution_doc.ents:
                            if missing_def_term in ent.text.lower():
                                institution = ent.text
                        if not bool(institution):
                            institution = 'Not found'
                    except:
                        institution = 'Not found'
                    institution_pattern = re.compile(r'\).*?\(.{,20}Institution.{,5}\)',re.IGNORECASE)
                else:
                    try:
                        institution_text_match = institution_pattern.findall(institution_text)[0]
                        # Open small Spacy model
                        institution_doc = nlp(institution_text_match)
                        # Extract Entities
                        for ent in institution_doc.ents:
                            if ent.label_ == 'ORG' and not bool(re.findall(r'[0-9]+',ent.text)):
                                institution = ent.text
                        if not bool(institution):
                            institution = 'Not found'
                    except:
                        institution = 'Not found'
                ########################
                # Principal Investigator - Name
                pi_entities = {}
                try:    
                    pi_text_match = pi_pattern.findall(temp_doc['pg1'].replace('\n','').strip())[0]
                    # Open small Spacy model
                    pi_doc = nlp(pi_text_match)
                    # Extract Entities
                    for ent in pi_doc.ents:
                        pi_entities[ent.label_] = ent.text
                    pi = pi_entities['PERSON']
                except:
                    pi = 'Not found'
            ##############################################################################
                # Extract Entity Contact info
                # Split text into sections - string = '\n'(0 or 1)1 or more digits'.' with no'.' directly behind and no digits in front of the first '.' and no digits after'.' all characters until '\n'
                # Try Roman Numerals First
                section_matches = roman_numeral_section_pattern.findall(raw_doc)
                if bool(section_matches):
                    section_dict = {}
                    for s in section_matches:
                        section_dict[s] = s.split('.')[1].replace('\n','').strip()
                else:
                    # Regular section pattern
                    section_matches = section_pattern.findall(raw_doc)
                    section_dict = {}
                    for s in section_matches:
                        section_dict[s] = s.split('.')[1].replace('\n','').strip()
                        
            ##############################################################################
                try:
                    # Get dict key from value
                    notices_section_pattern = list(section_dict.keys())[list(section_dict.values()).index('Notices')] # Notices
                    notices_next_section = list(section_dict.keys())[list(section_dict.values()).index('Notices')+1]
                    notices_text_pattern = re.compile(f"{notices_section_pattern}[\s\S]*{notices_next_section}")
                    notices_text_matches = notices_text_pattern.findall(raw_doc)[0].replace(f"{notices_next_section}",'')#.replace('\n','').strip()
                    # Contact Info
                    notices_lines = notices_text_matches.split('\n')
                    sponsor_info_list = []
                    institution_info_list = []
                    princ_invest_info_list = []
                    sponsor_re = re.compile(r'Sponsor',re.IGNORECASE)
                    institution_re = re.compile(r'Institution',re.IGNORECASE)
                    princ_invest_re = re.compile(r'Principal Investigator',re.IGNORECASE)
                    for i,line in enumerate(notices_lines):
                        if sponsor_re.search(line):
                            for l in notices_lines[i+1:]:
                                if l != ' ':
                                    sponsor_info_list.append(l)
                                else:
                                    break
                        elif institution_re.search(line):
                            for l in notices_lines[i+1:]:
                                if l != ' ':
                                    institution_info_list.append(l)
                                else:
                                    break
                        elif princ_invest_re.search(line):
                            for l in notices_lines[i+1:]:
                                if l != ' ':
                                    princ_invest_info_list.append(l)
                                else:
                                    break
                            break
                except:
                    sponsor_info_list = ['Not found']
                    institution_info_list = ['Not found']
                    princ_invest_info_list = ['Not found']
                    
            ##############################################################################
                # Recitals     
                # recitals_match = recitals_pattern.findall(clean_doc)
                
            ##############################################################################
                try:
                    # TIN 
                    tin_text_match = tin_pattern.findall(clean_doc)[0]
                    institution_tin = tin_text_match.split(' ')[-1]
                except:
                    institution_tin = 'Not found'
                
                # Insert data into list
                extracted_data.append([fn.name,effective_date,sponsor,institution,pi,sponsor_info_list,institution_info_list,princ_invest_info_list,institution_tin,raw_doc])
            except:
                unread_files.append([fn.name,'Contract not in ACTA or similar format'])
                continue
        # Insert into DF
        contract_df = pd.DataFrame(extracted_data,columns=['File_Name','Effective_Date','Sponsor_Name','Institution_Name','Principal_Investigator_Name','Sponsor_Contact','Institution_Contact','Principal_Investigator_Contact','Institution_TIN','Text'])
        unread_files_df = pd.DataFrame(unread_files,columns=['File_Name','Error'])
        st.write(contract_df)
        st.header('Unread Files')
        st.write(unread_files_df)
    
if __name__== '__main__':
    main()





















































