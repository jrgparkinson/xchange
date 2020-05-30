
import csv
# import urllib2
from bs4 import BeautifulSoup
import re 

# po10_urls = ['http://www.thepowerof10.info/athletes/profile.aspx?athleteid=554112']

# po10_base_url = 'http://powerof10.info/athletes/'



def lookup_po10(name, club):

    names = name.split(' ')
    if not names:
        return ""

    firstname = names[0]
    lastname = names[1]

    results = []

    po10url = 'https://thepowerof10.info/athletes/athleteslookup.aspx?surname=' + lastname + '&firstname=' + firstname

    try:
        import urllib.request
        with urllib.request.urlopen(po10url) as response:
            html = response.read()

        # page = urllib2.urlopen(po10url)
        soup = BeautifulSoup(html, 'html.parser')
        
        table = soup.find('table', attrs={'id': 'cphBody_dgAthletes'})
        
        if table:
            rows = table.find_all('tr')
            
            for row in rows:
                cols = row.find_all('td')
                for col in cols:
                    if col.text.strip() == 'Show':
                        a = col.find('a', href=True)
                        url = a['href']
                        
                        if 'runbritain' in url:
                            continue
                        
                        results.append({"url": url})
                        #print(url)
                        
                        
                        
    except Exception as error:
        print ('An exception was thrown accessing ' + po10url +  '!')
        print (str(error))
        return ""

    print(results)
    if len(results) == 1:
        return 'https://www.thepowerof10.info/athletes/' + results[0]["url"] 


    return ""




