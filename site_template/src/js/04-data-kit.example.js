/* ---------- kit data: phrases, checklists, driver cards, emergency, bookings ----------
   EXAMPLE. Made-up values for a fictional trip. Real refs here are shown to members only (see 04b-shell). */
const PHRASES=[ // [in the local script, how to say it, meaning]
 ['Olá','oh-LAH','hello'],['Obrigado','oh-bree-GAH-doo','thank you'],['Quanto custa?','KWAN-too KOOSH-tah','how much?'],
 ['A conta, por favor','ah KON-tah poor fah-VOR','the bill, please'],['Sem carne','sayn KAR-neh','no meat'],['Socorro!','soo-KOH-hoo','help!']];
const TODO=[ // "Before we fly": things with a deadline. One line each, never repeated elsewhere on the page
 'Arrival form for everyone, online, within 72 h of landing (TODO: real form name and link)',
 'Passports valid 6+ months past the return date',
 'Roaming pack or a local SIM plan',
 'Travel insurance',
 'Offline maps for every city'];
const PACK=['Passport + a photocopy','Sunscreen','Power bank and a plug adapter','Swimwear','Basic meds','Light jacket for the ferry'];
const KIT={
 airportCard:{cap:'Airports',say:[['Aeroporto de Porto Vela','Port Vela'],['Pista de Mirrow','Mirrow Bay']]},  // [local name to speak, label]
 sos:[['Police','24 h','112'],['Ambulance','medical emergency','112'],['Your embassy','office hours','+0 000 000 000']],  // [name, note, tel]
 hospitals:[['Port Vela General','Port Vela General Hospital'],['Mirrow Clinic','Mirrow Bay Clinic']],                // [label, maps query]
 fares:{unit:'EUR',rows:[['Airport to Port Vela, 20 min','15–20'],['Ferry to Mirrow Bay','25 each']],note:'Agree the fare before you get in.'},
 bookings:[ // members only. t: title, u: manage link, sub: who paid / what, ref: copyable
  {t:'Zephyr ZV 101 · 10 Mar',u:'https://example.com/manage',sub:'ZZH 08:00 → ZZV 11:30 · 3 pax · Alex paid',ref:'EXAMPLE-PNR-1'},
  {t:'Harbour Flat · 10 → 12 Mar',u:'https://example.com/listing/1',sub:'Sam paid',ref:'EXAMPLE-REF-1'}],
 tips:['Use the metered taxis or the app; agree other fares first.','Carry a passport copy.'],
 foot:'Prices given as ranges are estimates from operator and guide pages, not quotes. Photos: see the credit on each page.'
};
