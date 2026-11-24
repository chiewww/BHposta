#!/usr/bin/env python3
"""
monitor.py - BH Posta international Dopisnica (postcard) monitor.

Flow:
  1. Open the BH Posta calculator
  2. Click the "Međunarodni promet" tab
  3. Select Dopisnica
  4. For every destination in the "odredišna zemlja" drop-down:
       select "I stopa: do 20g" and click "Izračunaj"
  5. Write bh_posta_output.txt (no timestamps, so only real changes show up)

Safety: if the page or the drop-down cannot be read, or too many checks fail,
the script exits with an error and does NOT overwrite the output file.
"""

import re
import sys
import time
import unicodedata
from pathlib import Path

from playwright.sync_api import sync_playwright

# ============================================================
# CONFIG
# ============================================================

URL = "https://bhpwebout.posta.ba/KalkulatorCijena_WEB_app/Bos/Default.aspx"
OUTPUT_FILE = "bh_posta_output.txt"

TAB_SELECTOR = "#ASPxTabControl1_AT1T"          # "Međunarodni promet"
CALCULATE_SELECTOR = "#btnMeObPiIzracunaj"       # "Izračunaj"

# Tried in order after the tab is opened. First visible match is clicked.
DOPISNICA_SELECTORS = [
    'input[alt*="opisnica" i]',
    'input[title*="opisnica" i]',
    'img[alt*="opisnica" i]',
    'a:has-text("Dopisnica")',
    'text=Dopisnica',
    "#ImageButton8",
]

MIN_DESTINATION_OPTIONS = 100     # a select with this many options = country list
MIN_DESTINATIONS_SANITY = 150     # fewer than this = something is wrong, abort
MAX_ERRORS_ALLOWED = 5
RETRIES_PER_COUNTRY = 3
READ_DESTINATION_ATTEMPTS = 4
RESULT_WAIT_SECONDS = 8
MAX_RUNTIME_SECONDS = 25 * 60

SUSPENDED_MESSAGE_NORMALIZED = "PRIJEM POSILJAKA SE TRENUTNO NE VRSI"

IGNORED_DESTINATIONS = [
    "Azori",
    "BOUVET ISLAND",
    "Channel Islands",
    "HEARD ISLAND AND MCDONALD ISLANDS",
    "Italijanske poste",
    "Kanarski Otoci",
    "Madeira",
    "RIA",
]

# Dropdown names that stand for several Postcrossing destinations.
MULTI_ALIASES = {
    "HOLANDSKI ANTILI": [28, 57, 200],
    "NETHERLANDS ANTILLES": [28, 57, 200],
}

# ============================================================
# MASTER LIST:  number | Postcrossing name | local name; alias; alias ...
# The first alias is the local (Bosnian) name used for destinations that are
# missing from the BH Posta drop-down. All names are matched without
# diacritics, case or punctuation.
# ============================================================

MASTER_TABLE = """
1|Afghanistan|Afganistan
2|Åland Islands|Alandska ostrva; Aland
3|Albania|Albanija
4|Algeria|Alžir
5|American Samoa|Američka Samoa
6|Andorra|Andora
7|Angola|Angola
8|Anguilla|Angvila; Anguila
9|Antarctica|Antarktik; Antarktika
10|Antigua & Barbuda|Antigva i Barbuda; Antigua and Barbuda
11|Argentina|Argentina
12|Armenia|Armenija
13|Aruba|Aruba
14|Australia|Australija
15|Austria|Austrija
16|Azerbaijan|Azerbejdžan
17|Bahamas|Bahami
18|Bahrain|Bahrein
19|Bangladesh|Bangladeš
20|Barbados|Barbados
21|Belarus|Bjelorusija
22|Belgium|Belgija
23|Belize|Belize
24|Benin|Benin
25|Bermuda|Bermudi
26|Bhutan|Butan
27|Bolivia|Bolivija
28|Bonaire, Sint Eustatius and Saba|Bonaire; Sint Eustatius; Saint Eustatius; Sveti Eustatius; Saba
29|Bosnia-Herzegovina|Bosna i Hercegovina; Bosnia and Herzegovina
30|Botswana|Bocvana
31|Brazil|Brazil
32|British Indian Ocean Territory|Britanska teritorija Indijskog okeana
33|Brunei|Brunej; Brunei Darussalam
34|Bulgaria|Bugarska
35|Burkina Faso|Burkina Faso
36|Burundi|Burundi
37|Cabo Verde|Zelenortska Ostrva; Cape Verde
38|Cambodia|Kambodža
39|Cameroon|Kamerun
40|Canada|Kanada
41|Cayman Islands|Kajmanska ostrva
42|Central African Republic|Centralnoafrička Republika
43|Chad|Čad
44|Chile|Čile
45|China|Kina
46|Christmas Island|Božićno ostrvo
47|Cocos Islands|Kokosova ostrva; Cocos (Keeling) Islands
48|Colombia|Kolumbija
49|Comoros|Komori
50|Congo|Kongo; Congo (Rep.)
51|Dem. Rep. of Congo|Demokratska Republika Kongo; Congo (Dem. Rep.); Democratic Republic of the Congo
52|Cook Islands|Cookova ostrva
53|Costa Rica|Kostarika
54|Côte d'Ivoire|Obala Slonovače; Cote dIvoir; Cote dIvoire; Ivory Coast
55|Croatia|Hrvatska
56|Cuba|Kuba
57|Curaçao|Curacao
58|Cyprus|Kipar
59|Czechia|Češka; Czech Republic
60|Denmark|Danska
61|Djibouti|Džibuti
62|Dominica|Dominika
63|Dominican Republic|Dominikanska Republika
64|Ecuador|Ekvador
65|Egypt|Egipat
66|El Salvador|El Salvador
67|Equatorial Guinea|Ekvatorijalna Gvineja
68|Eritrea|Eritreja
69|Estonia|Estonija
70|Eswatini / Swaziland|Svazilend; Eswatini; Swaziland
71|Ethiopia|Etiopija
72|Falkland Islands / Malvinas|Falklandska ostrva; Falkland Islands
73|Faroe Islands|Farska ostrva
74|Fiji|Fidži
75|Finland|Finska
76|France|Francuska
77|French Guiana|Francuska Gvajana
78|French Polynesia|Francuska Polinezija; Tahiti
79|French Southern Territories|Francuske južne teritorije
80|Gabon|Gabon
81|Gambia|Gambija
82|Georgia|Gruzija
83|Germany|Njemačka
84|Ghana|Gana
85|Gibraltar|Gibraltar
86|Greece|Grčka
87|Greenland|Grenland
88|Grenada|Grenada
89|Guadeloupe|Gvadalupe
90|Guam|Guam
91|Guatemala|Gvatemala
92|Guernsey|Guernsey
93|Guinea|Gvineja
94|Guinea-Bissau|Gvineja Bisau
95|Guyana|Gvajana
96|Haiti|Haiti
97|Honduras|Honduras
98|Hong Kong|Hong Kong
99|Hungary|Mađarska
100|Iceland|Island
101|India|Indija
102|Indonesia|Indonezija
103|Iran|Iran
104|Iraq|Irak
105|Ireland|Irska
106|Isle of Man|Otok Man
107|Israel|Izrael
108|Italy|Italija
109|Jamaica|Jamajka
110|Japan|Japan
111|Jersey|Jersey
112|Jordan|Jordan
113|Kazakhstan|Kazahstan
114|Kenya|Kenija
115|Kiribati|Kiribati
116|Korea (North)|Sjeverna Koreja; Dem. People's Rep. of Korea; Korea (Dem. People's Rep.)
117|Korea (South)|Južna Koreja; Korea (Rep.)
118|Kosovo|Kosovo
119|Kuwait|Kuvajt
120|Kyrgyzstan|Kirgistan
121|Laos|Laos
122|Latvia|Latvija
123|Lebanon|Liban
124|Lesotho|Lesoto
125|Liberia|Liberija
126|Libya|Libija
127|Liechtenstein|Lihtenštajn
128|Lithuania|Litvanija
129|Luxembourg|Luksemburg
130|Macao|Makao
131|Madagascar|Madagaskar
132|Malawi|Malavi
133|Malaysia|Malezija
134|Maldives|Maldivi
135|Mali|Mali
136|Malta|Malta
137|Marshall Islands|Maršalova ostrva
138|Martinique|Martinik
139|Mauritania|Mauritanija
140|Mauritius|Mauricijus
141|Mayotte|Majot
142|Mexico|Meksiko
143|Micronesia|Mikronezija
144|Moldova|Moldavija
145|Monaco|Monako
146|Mongolia|Mongolija
147|Montenegro|Crna Gora
148|Montserrat|Montserrat
149|Morocco|Maroko
150|Mozambique|Mozambik
151|Myanmar|Mjanmar; Burma
152|Namibia|Namibija
153|Nauru / Naoero|Nauru
154|Nepal|Nepal
155|Netherlands|Nizozemska; Holandija
156|New Caledonia|Nova Kaledonija
157|New Zealand|Novi Zeland
158|Nicaragua|Nikaragva
159|Niger|Niger
160|Nigeria|Nigerija
161|Niue|Niue
162|Norfolk Island|Norfolk
163|Northern Mariana Islands|Sjeverna Marijanska ostrva
164|North Macedonia|Sjeverna Makedonija
165|Norway|Norveška
166|Oman|Oman
167|Pakistan|Pakistan
168|Palau|Palau
169|Palestine|Palestina
170|Panama|Panama
171|Papua New Guinea|Papua Nova Gvineja
172|Paraguay|Paragvaj
173|Peru|Peru
174|Philippines|Filipini
175|Pitcairn|Pitcairn
176|Poland|Poljska
177|Portugal|Portugal
178|Puerto Rico|Portoriko
179|Qatar|Katar
180|Réunion|Reunion
181|Romania|Rumunija
182|Russia|Rusija
183|Rwanda|Ruanda
184|Saint Barthélemy|Sveti Bartolomej
185|Saint Helena, Ascension and Tristan da Cunha|Sveta Helena; Saint Helena; Ascension; Tristan da Cunha
186|Saint Kitts and Nevis|Sveti Kits i Nevis
187|Saint Lucia|Sveta Lucija
188|Saint Martin|Sveti Martin
189|Saint Pierre & Miquelon|Sveti Pierre i Miquelon
190|Saint Vincent and the Grenadines|Sveti Vincent i Grenadini
191|Samoa|Samoa
192|San Marino|San Marino
193|Sao Tome and Principe|Sao Tome i Principe
194|Saudi Arabia|Saudijska Arabija
195|Senegal|Senegal
196|Serbia|Srbija
197|Seychelles|Sejšeli
198|Sierra Leone|Sijera Leone
199|Singapore|Singapur
200|Sint Maarten|Sint Maarten
201|Slovakia|Slovačka
202|Slovenia|Slovenija
203|Solomon Islands|Solomonska Ostrva
204|Somalia|Somalija
205|South Africa|Južnoafrička Republika; Južna Afrika
206|South Georgia and S. Sandwich Islands|Južna Georgija
207|South Sudan|Južni Sudan
208|Spain|Španija
209|Sri Lanka|Šri Lanka
210|Sudan|Sudan
211|Suriname|Surinam
212|Svalbard and Jan Mayen|Svalbard
213|Sweden|Švedska
214|Switzerland|Švicarska
215|Syria|Sirija
216|Taiwan|Tajvan
217|Tajikistan|Tadžikistan
218|Tanzania|Tanzanija
219|Thailand|Tajland
220|Timor-Leste|Istočni Timor; East Timor
221|Togo|Togo
222|Tokelau|Tokelau
223|Tonga|Tonga
224|Trinidad and Tobago|Trinidad i Tobago
225|Tunisia|Tunis
226|Turkey|Turska; Türkiye
227|Turkmenistan|Turkmenistan
228|Turks and Caicos Islands|Turks i Caicos
229|Tuvalu|Tuvalu
230|Uganda|Uganda
231|Ukraine|Ukrajina
232|United Arab Emirates|Ujedinjeni Arapski Emirati
233|United Kingdom|Ujedinjeno Kraljevstvo; Great Britain; Velika Britanija
234|Uruguay|Urugvaj
235|U.S.A.|Sjedinjene Američke Države; SAD; USA; United States
236|U.S. Minor Outlying Islands|Američka vanjska ostrva
237|Uzbekistan|Uzbekistan
238|Vanuatu|Vanuatu
239|Vatican|Vatikan; Holy See;
