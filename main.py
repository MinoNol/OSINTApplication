#from __future__ import print_function, with_statement

# Standard Library
import os
import re
import json
import shutil
import unicodedata
from glob import glob
from pprint import pprint

# Prerequisites
import chromedriver_autoinstaller
import easygui

# Crawlers and downloaders
import praw
import twitter
import selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import torch
import flair
from flair.data import Sentence
from flair.models import SequenceTagger
from multiprocessing import cpu_count
flair.device = torch.device('cpu')
torch.set_num_threads(cpu_count())

import Levenshtein as lev
import matplotlib.pyplot as plt

# Named Entity Recognition
import nltk
from nltk.corpus import stopwords
tagger = SequenceTagger.load('ner')

# API Key
tw_api = twitter.Api("GqizDtp9ovf8AxXfpZQJET0wW", "0t97ADo5Rhiq8Us6q8nsLfGUG82aYnTAR5olHJha2RLyUclaDB",
                     "1321516469944012801-tTKflVujCU2O2vBsgH5om4tpaQaUL3", "WWeTIWNAQ656sbMsAQF8O4lf07rL1TSvYjvEJYLK7e6kx")

# Configuration options
COMMENT_LIMIT = 500
ENTITY_THR = 0.75

def create_folder(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def find_profiles(username):
    print("Finding profiles")
    from subprocess import check_output
    # Run Maigrot on the provided username.
    cmd = """python maigret/maigret.py "{}" -fo report -J simple --site Twitter --site TikTok --site Reddit --site Instagram --site YouTube --site Twitch""".format(username)
    output = check_output(cmd, shell=True).decode()

    # Load Maigrot generated report.
    with open("report/report_{}_simple.json".format(username)) as cursor:
        found = json.load(cursor)

        # Extract user URLs for claimed profiles.
    found_data = {}
    for key, item in found.items():
        if item["status"]["status"] == "Claimed":
            found_data[key] = {"url": item["url_user"],
                               "username": item["username"]}

    # Write out found profiles to JSON file
    with open("found_profile_links.json", "w+") as cursor:
        json.dump(found, cursor, indent=4)


# Function to get text data from CSS selector, and clean it of Unicode data.
def get_text_from_css_selector(driver, css_selector):
    try:
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, css_selector)))
        profile_text = driver.find_element(By.CSS_SELECTOR, css_selector).text
        profile_text = unicodedata.normalize(
            "NFKD", profile_text).encode("ascii", "ignore").decode()
    except TimeoutException:
        profile_text = None
    return profile_text


# Function to scrape the profile descriptions from a couple popular sites.
# Link the candidates found by Maigrot together by Levenshtein distance.
# Write out the found data to JSON file.
def scrape():
    print("Scraping data from profiles")
    # Setting up Chrome WebDriver for Selenium.
    driver = webdriver.Chrome()
    scraped = {}
    # Reading links from JSON file
    profiles_scanned = glob("report/*")
    for profile_file in profiles_scanned:
        print("Currently extracting from \"{}\"".format(profile_file))
        with open(profile_file, "r") as cursor:
            profiles = json.load(cursor)
            # Extract usernames from the various services in the report file.
            username = profiles[next(iter(profiles))]["username"]
            scraped[username] = {}
            for service in profiles:
                # For each, extract the URL to the user profile.
                profile_url = profiles[service]["url_user"]
                print("EXTRACTING FROM {}".format(profile_url))
                profile_text = None
                scraped[username][service] = {}

                # Choose CSS selector, and modify link, depending on the service.
                if service == "Twitter":
                    # Configure
                    #css_selector = ".r-1adg3ll > .css-1dbjc4n > .r-1fmj7o5"
                    css_selector = ".css-1dbjc4n:nth-child(2) > .css-1dbjc4n:nth-child(3) > .css-1dbjc4n > .css-901oao > .css-901oao"
                    driver.get(profile_url)
                    # If description not found, the comments still might be
                    profile_text = ""
                    profile_text = get_text_from_css_selector(
                        driver, css_selector)
                    timeline = tw_api.GetUserTimeline(
                        screen_name=profiles[service]["username"])
                    num_tweets = 0
                    for tweet in timeline:
                        profile_text += "\n" + tweet.text 
                        num_tweets += 1
                        if num_tweets >= COMMENT_LIMIT:
                            break
                    try:
                        scraped[username][service]["follower_count"] = profiles[service]["status"]["ids"]["follower_count"]
                    except KeyError:
                        pass
                    try:
                        scraped[username][service]["following_count"] = profiles[service]["status"]["ids"]["following_count"]
                    except KeyError:
                        pass                    
                    try:
                        scraped[username][service]["favourites_count"] = profiles[service]["status"]["ids"]["favourites_count"]
                    except KeyError:
                        pass
                    try:
                        scraped[username][service]["tags"] = profiles[service]["status"]["tags"]
                    except KeyError:
                        pass

                elif service == "TikTok":
                    css_selector = ".share-desc"
                    driver.get(profile_url)
                    profile_text = get_text_from_css_selector(
                        driver, css_selector)

                    try:
                        scraped[username][service]["follower_count"] = profiles[service]["status"]["ids"]["follower_count"]
                    except KeyError:
                        pass
                    try:
                        scraped[username][service]["following_count"] = profiles[service]["status"]["ids"]["following_count"]
                    except KeyError:
                        pass  
                    try:
                        scraped[username][service]["heart_count"] = profiles[service]["status"]["ids"]["heart_count"]
                    except KeyError:
                        pass  
                    try:
                        scraped[username][service]["video_count"] = profiles[service]["status"]["ids"]["video_count"]
                    except KeyError:
                        pass  
                    try:
                        scraped[username][service]["digg_count"] = profiles[service]["status"]["ids"]["digg_count"]
                    except KeyError:
                        pass
                    try:
                        scraped[username][service]["tags"] = profiles[service]["status"]["tags"]
                    except KeyError:
                        pass     
                elif service == "Reddit":
                    css_selector = ".bVfceI5F_twrnRcVO1328"
                    driver.get(profile_url)
                    # If description not found, the comments still might be
                    profile_text = ""
                    profile_text = get_text_from_css_selector(
                        driver, css_selector)
                    # Initialize a Reddit object
                    reddit = praw.Reddit(
                        client_id="4lITDZO8vKxMdg",
                        client_secret="rtw7bfTuLerP3NICKZjRLd7TOFFydQ",
                        user_agent="python_script:honours_dissertation:1 (by Anonymous)",
                    )
                    for comment in reddit.redditor(profiles[service]["username"]).comments.new(limit=COMMENT_LIMIT):
                        profile_text += "\n" + comment.body
                    try:
                        scraped[username][service]["digg_count"] = profiles[service]["status"]["ids"]["digg_count"]
                    except KeyError:
                        pass
                    try:
                        scraped[username][service]["digg_count"] = profiles[service]["status"]["ids"]["digg_count"]
                    except KeyError:
                        pass
                    try:
                        scraped[username][service]["digg_count"] = profiles[service]["status"]["ids"]["digg_count"]
                    except KeyError:
                        pass
                elif service == "Instagram":
                    css_selector = ".-vDIg"
                    driver.get(profile_url)
                    profile_text = get_text_from_css_selector(
                        driver, css_selector)
                elif service == "YouTube":
                    css_selector = "#description-container > #description"
                    driver.get(profile_url + "/about")
                    profile_text = get_text_from_css_selector(
                        driver, css_selector)
                elif service == "Twitch":
                    css_selector = ".tw-flex-column > .tw-font-size-5"
                    driver.get(profile_url + "/about")
                    profile_text = get_text_from_css_selector(
                        driver, css_selector)
                    if profile_text.startswith("We don't know much about them, but we're sure "):
                        profile_text = ""

                    try:
                        scraped[username][service]["views_count"] = profiles[service]["status"]["ids"]["views_count"]
                    except KeyError:
                        pass  
                    try:
                        scraped[username][service]["likes_count"] = profiles[service]["status"]["ids"]["likes_count"]
                    except KeyError:
                        pass  
                    try:
                        scraped[username][service]["tags"] = profiles[service]["status"]["tags"]
                    except KeyError:
                        pass    

                # If profile text managed to be retrieved, save it.
                if profile_text:
                    scraped[username][service]["bio"] = profile_text
    driver.close()

    # Levenshtein distance for finding similar enough usernames to be counted as the same user, one character edit is one added to the value
    # Remove erroneous keys, add values under those keys, under another, a true one, gotten from user input.
    THRESHOLD = 5
    profile_names = scraped.keys()
    candidates = []
    done = []
    for profile1 in profile_names:
        for profile2 in profile_names:
            if profile1 == profile2 or sorted((profile1, profile2)) in done:
                continue
            else:
                distance = lev.distance(profile1, profile2)
                print("{} - {}: {}".format(profile1, profile2, distance))
                if distance < THRESHOLD:
                    done.append(sorted((profile1, profile2)))
                    candidates.append((profile1, profile2))

    scraped["likely_candidates"] = candidates

    # Print for the user in Gooey
    print("LIKELY_CANDIDATES:")
    pprint(candidates)

    # Save results.
    with open("scraped.json", "w+") as cursor:
        json.dump(scraped, cursor, indent=4)


def remove_non_ascii(text):
    return ''.join([i if ord(i) < 128 else ' ' for i in text])

#https://www.askpython.com/python/examples/word-cloud-using-python
def create_graph(most_used, path, threshold, service, dpi = 100):
    X, Y = [], []
    for key, val in most_used.items():
        if val >= threshold:
            X.append(key)
            Y.append(val)

    if X and Y:
        plt.figure(figsize=(16, 9))
        plt.title(service)
        plt.xlabel("Words")
        plt.ylabel("Frequency")
        plt.bar(X, Y)
        #plt.show() 
        plt.savefig(path, bbox_inches='tight', dpi=dpi)
        plt.show()
    

def natural_language():
    # Open previously saved results.
    with open("scraped.json", "r") as infile:
        saved_data = json.load(infile)
    # loop for checking values and keys in json file
    for username, data in saved_data.items():
        # Skip this key, it's not a profile username.
        if username == "likely_candidates":
            continue
        print("Processing {}".format(username))
        text = ""
        # For all service and their text in the data.
        for service, service_data in data.items():
            # If the text from the data is not empty
            if "bio" in service_data.keys():
                # Mush all the text together into one string.
                service_data["bio"] = remove_non_ascii(service_data["bio"])
                # Remove any links.
                service_data["bio"] = re.sub(r"http\S+", "", service_data["bio"])
                text += "\n" + service_data["bio"]

                # Generate most used words on the service data only.
                most_used = {}
                stop_words = stopwords.words("english")
                for word in service_data["bio"].replace("\n", " ").split(" "):
                    if word:
                        key = word.lower()
                        if key not in stop_words:
                            if key not in most_used:
                                most_used[key] = 1
                            else:
                                most_used[key] += 1
                        
                sorted_by_val = dict(sorted(most_used.items(), key=lambda item: item[1], reverse=True))
                with open("most_used/{}_{}_most_used.json".format(username, service), "w+") as cursor:
                    json.dump(sorted_by_val, cursor, indent=4)

                create_graph(most_used, "bar_charts/{}_{}.jpg".format(username, service), 3, service)

                print("Finished processing - {}".format(service))

        # TOP N most used words.
        print("Generating most used Named Entities, if possible")
        if text:
            named_entities = ""
            doc = Sentence(text)

            # run NER over sentence
            tagger.predict(doc)
            # iterate over entities and print
            for entity in doc.get_spans('ner'):
                print(entity)
                if entity.score > ENTITY_THR:
                    named_entities += entity.text + " "
            
            most_used = {}
            for word in named_entities.replace("\n", " ").split(" "):
                key = word.lower()
                if key not in most_used:
                    most_used[key] = 1
                else:
                    most_used[key] += 1
                    
            sorted_by_val = dict(sorted(most_used.items(), key=lambda item: item[1], reverse=True))
            with open("most_used/{}_named_entities.json".format(username), "w+") as cursor:
                json.dump(sorted_by_val, cursor, indent=4)
            
            create_graph(most_used, "bar_charts/{}_named_entites.jpg".format(username), 0, "Named Entities")




def main():
    # Check if the current version of chromedriver exists
    # and if it doesn't exist, download it automatically,
    # then add chromedriver to path
    try:
        chromedriver_autoinstaller.install()
    except FileNotFoundError:
        print("ChromeDriver Autoinstaller failed, please install the correct 'chromedriver' manually.")

    nltk.download('stopwords')

    again = True
    while again:
        if easygui.ynbox("Would you like to clean program data?", 'Title', ('Yes', 'No')):
            shutil.rmtree("./report", ignore_errors=True)
            shutil.rmtree("./most_used", ignore_errors=True)
            shutil.rmtree("./bar_charts", ignore_errors=True)

            if os.path.isfile("scraped.json"):
                os.remove("scraped.json")
            if os.path.isfile("found_profile_links.json"):
                os.remove("found_profile_links.json")

        create_folder("./report/")
        create_folder("./most_used/")
        create_folder("./bar_charts/")

        msg = "Enter your subject profile name"
        title = "Social Media Scraper"
        fieldNames = ["Subject Profile Name"]
        fieldValues = easygui.multenterbox(msg, title, fieldNames)
        if fieldValues is None:
            exit(0)
        # make sure that none of the fields were left blank
        while 1:
            errmsg = ""
            for i, name in enumerate(fieldNames):
                if fieldValues[i].strip() == "":
                    errmsg += "{} is a required field.\n\n".format(name)
            if errmsg == "":
                break  # no problems found
            fieldValues = easygui.multenterbox(
                errmsg, title, fieldNames, fieldValues)
            if fieldValues is None:
                break
        print("Profile name is: {}".format(fieldValues))
        profile_name = fieldValues[0]

        find_profiles(profile_name)
        scrape()
        natural_language()

        again = easygui.ynbox(
            "Would you like to try again?", 'Title', ('Yes', 'No'))


if __name__ == "__main__":
    main()
