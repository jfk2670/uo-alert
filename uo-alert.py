#!/bin/python3

import os
import ssl
import time
import json
from time import sleep
import datetime
import random
import urllib.request
import requests
import atexit
import validators

import os.path
from bs4 import BeautifulSoup

ALERT_WEBHOOK = 'WEBHOOK-HERE'
LOG_WEBHOOK = 'WEBHOOK-HERE'
USERAGENT_URL = 'https://raw.githubusercontent.com/DavidWittman/requests-random-user-agent/master/requests_random_user_agent/useragents.txt'
USERAGENT_PATH = 'useragents.txt'
ITEMS_PATH = 'items.txt'

# action to take on exit(0)
def exit_handler():
    sendLogToDiscord(messagesToLog)

# add log entry to buffer
def appendToLog(message):
    global messagesToLog
    now=datetime.datetime.now().strftime("%F %H:%M:%S")
    messagesToLog+=f'{now} {message}\n'

# return list of items to check from items.txt
def retrieveItems():
    appendToLog('[+] Checking validity of items.txt...')
    if os.path.exists(ITEMS_PATH):
        appendToLog('[+] items.txt exists, retrieving items...')
        with open(ITEMS_PATH, 'r') as itemListFile:
            items = itemListFile.readlines()
            return items
    appendToLog('[!] items.txt does not exist or is empty, exiting...')
    exit(0)

def updateItems(newItemStatuses):
    appendToLog('[+] Writing new item statuses...')
    with open(ITEMS_PATH, 'r+') as itemListFile:
        itemListFile.truncate(0)
        itemListFile.write(newItemStatuses)
        return

# check if file is older than 7 days, if so download new one
def retrieveUserAgents():
    appendToLog('[+] Checking validity of useragents.txt...')
    if os.path.exists(USERAGENT_PATH) and os.path.getsize(USERAGENT_PATH) > 1:
        today = datetime.datetime.today()
        modified_date = datetime.datetime.fromtimestamp(os.path.getmtime('useragents.txt'))
        duration = today - modified_date
        if duration.days > 7:
            appendToLog('[!] useragents.txt is greater than 7 days old, updating...')
            urllib.request.urlretrieve(USERAGENT_URL, USERAGENT_PATH)
    else:
        appendToLog('[!] useragents.txt does not exist or is empty, downloading...')
        urllib.request.urlretrieve(USERAGENT_URL, USERAGENT_PATH)

    try:
        appendToLog('[+] useragents.txt is valid, retrieving list...')
        userAgentFile = open(USERAGENT_PATH)
        return userAgentFile.readlines()
    except Exception as e:
        appendToLog('[X] Encountered an error, exiting...')
        appendToLog(f'[X] {e}')
        exit(0)

# generate random User Agent and pass built request to availability check
def build_request(link, userAgent):
    req = urllib.request.Request(
            link,
            data=None,
            headers={
                'User-Agent': userAgent,
                #'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.4 Safari/605.1.15'
                }
            )
    return req

# parse UO page for meta tags and return instock or not
def checkUOAvailability(line, randomUserAgent):
    link, status = line.rstrip().split(',')

    appendToLog(f'[+] Checking if <{link}> is still {status.upper()}...')
    if validators.url(link):
        req = build_request(link, randomUserAgent)
    else:
        appendToLog(f'[!] Invalid link [{link}], skipping...')
        return False

    global newItemStatuses

    try:
        with urllib.request.urlopen(req) as response:
            #webpage = urlopen(link.read())
            soup = BeautifulSoup(response, 'lxml')

            title = soup.find('meta', property='og:title')
            availability = soup.find('meta', property='product:availability')
            price = soup.find('meta', property='product:price:amount')
            thumbnail = soup.find('meta', property='og:image')

            newItemStatuses+=f'{link},{availability["content"]}'
            newItemStatuses+='\n'

            if status != availability['content']:
                appendToLog(f'[!] STATUS CHANGE: {title["content"]} is now {availability["content"].upper()}, sending to #uo-restocks...')
                sendAlertToDiscord(
                        title['content'],
                        link,
                        price['content'],
                        availability['content'],
                        thumbnail['content']
                        )
                return True
            elif status == availability['content']:
                appendToLog(f'[+] No change in stock status for {title["content"]}')
                return False
            else:
                appendToLog(f'[!] ERROR: Could not determine stock status for {title["content"]}')
                return False

    except Exception as e:
        appendToLog(f'[!] ERROR: Could not fetch product page for <{link}>')
        appendToLog(f'[X] {e}')
        newItemStatuses+=f'{link},{status}'
        newItemStatuses+='\n'
        return False

# send instock alert to discord webhook
def sendAlertToDiscord(title, link, price, availability, thumbnail):
    headline = f'**{availability.upper()}**: {title}'
    data = {
            'username': 'UO Vinyl Bot',
            'avatar_url': 'https://cdn.iconscout.com/icon/premium/png-256-thumb/vinyl-record-3170257-2654884.png',
            'content': headline,
            #}
            'embeds': [
                {
                    'author': {
                        'name': 'UO Vinyl Bot',
                        'url': link,
                        'icon_url': 'https://cdn.iconscout.com/icon/premium/png-256-thumb/vinyl-record-3170257-2654884.png'
                        },
                    'title': title,
                    'url': link,
                    #'description': 'description goes here',
                    'color': 7368550,
                    'fields': [
                        {
                            'name': 'Status',
                            'value': availability
                            },
                        {
                            'name': 'Store',
                            'value': 'Urban Outfitters',
                            },
                        {
                            'name': 'Price',
                            'value': price,
                            },
                        ],
                    'thumbnail': {
                        'url': thumbnail
                        },
                    # 'image': {
                    # 	'url': thumbnail
                    #},
                    'footer': {
                        'text': 'Hi there!',
                        'icon_url': 'https://tcrf.net/images/b/b4/SBlcp_spongebobportrait.png'
                        }
                    }
                ]
            }

    response = requests.post(ALERT_WEBHOOK, json=data)

def sendLogToDiscord(logs):
    # if over 2k characters, split into smaller chunks (discord limitation)
    if len(logs) > 1999:
        splitLines = logs.splitlines()
        lineCount = len(splitLines)
        linesParsed = 0
        count = 0
        splitLogs = ''
        for line in logs.splitlines():
            splitLogs += line
            splitLogs += '\n'
            count += 1
            linesParsed += 1
            if count == 10:
                data = {'content':splitLogs}
                response = requests.post(LOG_WEBHOOK, json=data)
                count = 0
                splitLogs = ''
                next
            if linesParsed == lineCount:
                data = {'content':splitLogs}
                response = requests.post(LOG_WEBHOOK, json=data)
                return
    else:
        data = {'content':logs}
        response = requests.post(LOG_WEBHOOK, json=data)

# MAIN
atexit.register(exit_handler)
messagesToLog = ''
newItemStatuses = ''

userAgentList = retrieveUserAgents()
itemList = retrieveItems()

appendToLog('[+] Selecting random User Agent...')
randomUserAgent = str(random.choice(userAgentList)).strip()
for line in itemList:
    checkUOAvailability(line, randomUserAgent)
    sleep(8)

updateItems(newItemStatuses)
exit(0)