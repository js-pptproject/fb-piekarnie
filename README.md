# Monitor fanpage'y (darmowy zamiennik rss.app)

Male narzedzie, ktore co kilka godzin sprawdza publiczne fanpage'e na
Facebooku, zbiera nowe posty i pokazuje je na prostej stronie (dashboard),
ktora mozesz otworzyc w przegladarce. Koszt: 0 zl - dziala na darmowych
limitach GitHub Actions (uruchamianie skryptu) i GitHub Pages (hosting
strony).

## Zanim zaczniesz - szczera ocena ograniczen

- Facebook nie udostepnia oficjalnego, darmowego API do stron, ktorych
  nie jestes adminem (to tzw. Page Public Content Access - Meta przyznaje
  je praktycznie tylko duzym, zatwierdzonym podmiotom, nie da sie tego
  "zalatwic" dla prywatnego narzedzia). Dlatego - dokladnie tak jak
  rss.app "pod maska" - to narzedzie dziala przez odczytywanie strony
  tak, jak widzialaby ja niezalogowana osoba w przegladarce.
- To oznacza dwie rzeczy: (1) jest to formalnie niezgodne z regulaminem
  Facebooka (automatyczne pobieranie danych), choc dla prywatnego,
  niewielkiego monitoringu kilku stron ryzyko w praktyce sprowadza sie
  do tego, ze Facebook moze zablokowac/spowolnic dostep, a nie do
  konsekwencji prawnych; (2) Facebook regularnie zmienia wyglad strony,
  wiec narzedzie moze sie "zepsuc" i wymagac drobnej poprawki co jakis
  czas.
- Nie testowalem tego skryptu na zywym Facebooku z tego srodowiska (moje
  sandboxowe srodowisko ma zablokowany bezposredni dostep do
  facebook.com), wiec pierwsze uruchomienie warto potraktowac jako test.
  Jesli cos nie zadziala od razu, sekcja "Co zrobic, jesli sie psuje"
  ponizej mowi jak to zdiagnozowac - a ja moge to poprawic, jesli
  wkleisz mi, co pokazuje debug/.
- Jesli po tescie okaze sie to zbyt niestabilne, tanszym (choc juz nie
  darmowym) fallbackiem jest Apify (Facebook Posts Scraper) - platnosc
  za realne zuzycie zamiast sztywnej subskrypcji, wiec przy monitoringu
  kilku-kilkunastu stron to raczej pojedyncze dolary miesiecznie, a nie
  200 USD.

## Co jest w tym folderze

- `scraper.py` - skrypt w Pythonie (Playwright), ktory odwiedza strony
  z `pages.txt` i wyciaga widoczne posty do `data/feed.json`.
- `pages.txt` - lista fanpage'y do sledzenia (Ty uzupelniasz).
- `.github/workflows/scrape.yml` - harmonogram, ktory uruchamia scraper
  co 4 godziny na darmowych serwerach GitHuba i zapisuje wyniki.
- `index.html` - dashboard (jeden plik, bez instalacji), ktory czyta
  `data/feed.json` i `data/status.json` i pokazuje posty.
- `data/` - tu ladują sie wyniki (feed.json - posty, status.json - czy
  dana strona dala sie odczytac).

## Instalacja (10-15 minut, raz)

1. Zaloz darmowe konto na [github.com](https://github.com), jesli
   jeszcze go nie masz.
2. Stworz nowe **publiczne** repozytorium (np. `fb-monitor`). Publiczne,
   bo darmowy hosting GitHub Pages dziala bez ograniczen tylko dla
   publicznych repozytoriow (kod bedzie widoczny, ale to tylko skrypt -
   nic wrazliwego).
3. Wgraj do niego cala zawartosc tego folderu (przez przeglądarke:
   "Add file" -> "Upload files", albo przez git, jesli wolisz).
4. Otworz w repozytorium plik `pages.txt` i wklej tam pelne adresy
   fanpage'y konkurencji, ktore chcesz sledzic (jeden URL na linie).
5. Wlacz GitHub Pages: Settings -> Pages -> Source: "Deploy from a
   branch" -> branch `main`, folder `/ (root)` -> Save. Po chwili
   dostaniesz adres typu `https://twoj-login.github.io/fb-monitor/`.
6. Uruchom scraper pierwszy raz recznie: zakladka **Actions** -> workflow
   "Sprawdz fanpage'e" -> **Run workflow**. Poczekaj 2-3 minuty.
7. Odswiez adres z kroku 5 - powinny pojawic sie pierwsze posty.

Od tej pory workflow sam odpala sie co 4 godziny (mozesz zmienic
czestotliwosc edytujac linijke `cron:` w
`.github/workflows/scrape.yml` - np. `0 */2 * * *` dla co 2 godziny;
pamietaj, ze czasy sa w UTC, czyli 2h wczesniej niz czas polski latem i
1h wczesniej zima).

## Co zrobic, jesli sie psuje

Jesli w dashboardzie przy jakiejs stronie widzisz status inny niz "ok"
(np. "blokada logowania" albo "brak postow"):

1. Wejdz w zakladke **Actions** -> ostatnie uruchomienie -> sekcja
   "Artifacts" na dole strony -> pobierz `debug-<numer>.zip`.
2. W srodku bedzie zrzut ekranu (`.png`) i pelny HTML (`.html`) tego,
   co faktycznie zwrocil Facebook dla danej strony w momencie
   sprawdzania.
3. Jesli to ekran logowania - ta konkretna strona moze wymagac
   zalogowanego konta, zeby pokazac posty (niektore fanpage'e tak maja
   skonfigurowana widocznosc). Nie ma na to darmowego, bezpiecznego
   obejscia bez ryzyka dla konta uzytego do logowania.
4. Jesli to wyglada jak normalna strona, ale bez postow - Facebook
   najpewniej zmienil znaczniki HTML. Wklej mi zawartosc pliku `.html`
   (albo chocby opisz co widac na screenie), a poprawie selektory w
   `scraper.py`.

## Pomysly na rozwiniecie (opcjonalne)

- Powiadomienia (np. na maila albo Discorda) o nowych postach zamiast
  samego sprawdzania dashboardu - da sie dograc krok w workflow.
- Filtrowanie/wyszukiwanie po slowach kluczowych w dashboardzie.
- Osobny plik z nazwami wyswietlanymi zamiast surowych "slugów" z URL.

Daj znac, jesli chcesz, zebym ktorys z tych dodal.
