#!/usr/bin/env python3
"""
One-off builder for data/vegas_player_props_2026.csv from the full
fantasypoints.com season-prop articles (receiving/rushing yards & TDs,
passing yards & TDs), fetched in full on 2026-07-28 (superseding the earlier
partial/curated snapshot, which only kept ~50 WR/TE + ~20 RB "most market
interest" rows out of what these articles actually cover).

Line = midpoint of ("highest total where the under is the play", "lowest
total where the over is the play"), i.e. the same consensus-line
methodology used throughout this project -- NOT the "FP Projection" column,
which is fantasypoints' own proprietary point estimate, not a market price.

Run once with the main app venv to regenerate the CSV:
    venv\\Scripts\\python.exe scripts\\_build_vegas_props_2026.py
"""
import csv
import os

# name -> (highest_total_under, lowest_total_over)
RECEIVING_YARDS = {
    "Puka Nacua": (1375.5, 1275.5), "Jaxon Smith-Njigba": (1350.5, 1250.5),
    "Ja'Marr Chase": (1350.5, 1250.5), "Amon-Ra St. Brown": (1249.5, 1200.5),
    "CeeDee Lamb": (1225.5, 1125.5), "Justin Jefferson": (1150.5, 1100.5),
    "Nico Collins": (1100.5, 1050.5), "A.J. Brown": (1124.5, 1049.5),
    "Drake London": (1149.5, 1100.5), "Chris Olave": (1050.5, 1000.5),
    "Zay Flowers": (1000.5, 925.5), "George Pickens": (1050.5, 975.5),
    "Jameson Williams": (925.5, 850.5), "Tee Higgins": (874.5, 850.5),
    "Garrett Wilson": (999.5, 950.5), "DeVonta Smith": (1049.5, 1000.5),
    "Terry McLaurin": (950.5, 925.5), "Ladd McConkey": (875.5, 825.5),
    "Brock Bowers": (900.5, 850.5), "Christian Watson": (799.5, 775.5),
    "Jaylen Waddle": (874.5, 825.5), "Emeka Egbuka": (874.5, 825.5),
    "Davante Adams": (800.5, 750.5), "Alec Pierce": (900.5, 850.5),
    "Mike Evans": (925.5, 825.5), "Tetairoa McMillan": (949.5, 900.5),
    "Brian Thomas Jr.": (724.5, 674.5), "Rome Odunze": (779.5, 750.5),
    "DK Metcalf": (850.5, 800.5), "Luther Burden III": (824.5, 800.5),
    "Courtland Sutton": (799.5, 725.5), "Tyler Warren": (750.5, 724.5),
    "Colston Loveland": (799.5, 750.5), "Josh Downs": (775.5, 749.5),
    "DJ Moore": (825.5, 750.5), "Trey McBride": (1025.5, 975.5),
    "Jayden Reed": (649.5, 624.5), "Jordan Addison": (674.5, 649.5),
    "Kyle Pitts Sr.": (774.5, 725.5), "Romeo Doubs": (624.5, 600.5),
    "Carnell Tate": (800.5, 700.5), "Michael Pittman Jr.": (774.5, 725.5),
    "Travis Kelce": (675.5, 650.5), "Makai Lemon": (649.5, 600.5),
    "Marvin Harrison Jr.": (825.5, 800.5), "Dallas Goedert": (575.5, 574.5),
    "Khalil Shakir": (675.5, 600.5), "Omar Cooper Jr.": (575.5, 500.5),
    "Jake Ferguson": (524.5, 475.5), "Mark Andrews": (524.5, 474.5),
    "Kenyon Sadiq": (475.5, 400.5), "Dalton Kincaid": (549.5, 525.5),
    "KC Concepcion": (624.5, 550.5), "Denzel Boston": (499.5, 400.5),
}

RECEIVING_TDS = {
    "Ja'Marr Chase": (10.5, 9.5), "Jaxon Smith-Njigba": (8.5, 7.5),
    "Tee Higgins": (8.5, 7.5), "Puka Nacua": (8.5, 7.5),
    "Amon-Ra St. Brown": (9.5, 9.5), "Davante Adams": (9.5, 8.5),
    "Mike Evans": (6.5, 5.5), "Justin Jefferson": (7.5, 6.5),
    "CeeDee Lamb": (7.5, 7.5), "Drake London": (7.5, 6.5),
    "George Pickens": (7.5, 6.5), "A.J. Brown": (7.5, 6.5),
    "Emeka Egbuka": (6.5, 6.5), "Christian Watson": (6.5, 5.5),
    "Nico Collins": (6.5, 6.5), "Garrett Wilson": (4.5, 4.5),
    "Brock Bowers": (7.5, 6.5), "DeVonta Smith": (5.5, 4.5),
    "Jameson Williams": (5.5, 5.5), "Terry McLaurin": (5.5, 5.5),
    "Rome Odunze": (7.5, 5.5), "Courtland Sutton": (7.5, 6.5),
    "Ladd McConkey": (5.5, 4.5), "DK Metcalf": (6.5, 4.5),
    "Mark Andrews": (5.5, 5.5), "Chris Olave": (6.5, 5.5),
    "Zay Flowers": (5.5, 5.5), "Trey McBride": (6.5, 5.5),
    "Tetairoa McMillan": (6.5, 6.5), "DJ Moore": (6.5, 6.5),
    "Colston Loveland": (5.5, 4.5), "Brian Thomas Jr.": (4.5, 4.5),
    "Jaylen Waddle": (5.5, 4.5), "Jake Ferguson": (4.5, 4.5),
    "Travis Kelce": (4.5, 3.5), "Sam LaPorta": (4.5, 4.5),
    "Quentin Johnston": (5.5, 5.5), "Alec Pierce": (5.5, 4.5),
    "Jakobi Meyers": (5.5, 5.5), "Carnell Tate": (4.5, 4.5),
    "Christian McCaffrey": (4.5, 4.5), "Dallas Goedert": (5.5, 4.5),
    "Dalton Kincaid": (3.5, 3.5), "Chris Godwin Jr.": (5.5, 4.5),
    "Xavier Worthy": (4.5, 3.5), "Jahmyr Gibbs": (4.5, 3.5),
    "Bijan Robinson": (3.5, 3.5), "Calvin Ridley": (3.5, 3.5),
}

RUSHING_YARDS = {
    "Jonathan Taylor": (1250.5, 1175.5), "Bijan Robinson": (1200.5, 1100.5),
    "James Cook III": (1250.5, 1150.5), "Derrick Henry": (1274.5, 1200.5),
    "Jahmyr Gibbs": (1249.5, 1125.5), "Saquon Barkley": (1099.5, 1000.5),
    "De'Von Achane": (1000.5, 950.5), "David Montgomery": (800.5, 700.5),
    "Javonte Williams": (1000.5, 900.5), "Breece Hall": (925.5, 825.5),
    "Kenneth Walker III": (950.5, 875.5), "Ashton Jeanty": (1024.5, 925.5),
    "Kyren Williams": (1000.5, 999.5), "Omarion Hampton": (949.5, 875.5),
    "Jeremiyah Love": (925.5, 825.5), "Bhayshul Tuten": (724.5, 699.5),
    "Jadarian Price": (750.5, 750.5), "Christian McCaffrey": (974.5, 900.5),
    "Tony Pollard": (800.5, 750.5), "D'Andre Swift": (800.5, 725.5),
    "Travis Etienne Jr.": (875.5, 850.5), "Bucky Irving": (825.5, 800.5),
    "Chase Brown": (850.5, 800.5), "Blake Corum": (675.5, 674.5),
    "Jayden Daniels": (550.5, 549.5), "Lamar Jackson": (575.5, 525.5),
    "Jaxson Dart": (449.5, 425.5), "Josh Allen": (500.5, 450.5),
    "Jalen Hurts": (400.5, 399.5), "Drake Maye": (424.5, 400.5),
}

RUSHING_TDS = {
    "Jonathan Taylor": (11.5, 11.5), "Jahmyr Gibbs": (12.5, 11.5),
    "Derrick Henry": (13.5, 12.5), "James Cook III": (10.5, 10.5),
    "Saquon Barkley": (7.5, 7.5), "Bijan Robinson": (10.5, 7.5),
    "Josh Allen": (11.5, 10.5), "Kyren Williams": (10.5, 9.5),
    "Kenneth Walker III": (7.5, 6.5), "Javonte Williams": (9.5, 9.5),
    "David Montgomery": (8.5, 7.5), "Christian McCaffrey": (8.5, 8.5),
    "Ashton Jeanty": (7.5, 7.5), "Omarion Hampton": (7.5, 7.5),
    "Jeremiyah Love": (5.5, 5.5), "De'Von Achane": (5.5, 5.5),
    "Jalen Hurts": (8.5, 7.5), "D'Andre Swift": (7.5, 5.5),
    "Travis Etienne Jr.": (5.5, 5.5), "Chuba Hubbard": (4.5, 4.5),
    "Jadarian Price": (5.5, 5.5), "Chase Brown": (6.5, 5.5),
    "Rhamondre Stevenson": (6.5, 5.5), "Bucky Irving": (5.5, 5.5),
    "Blake Corum": (5.5, 5.5), "Tony Pollard": (5.5, 5.5),
    "Isiah Pacheco": (4.5, 4.5), "Breece Hall": (5.5, 5.5),
    "Jaxson Dart": (6.5, 4.5), "Kyle Monangai": (4.5, 4.5),
    "Jayden Daniels": (4.5, 4.5), "J.K. Dobbins": (5.5, 5.5),
    "Jordan Mason": (4.5, 4.5), "Lamar Jackson": (3.5, 3.5),
    "Drake Maye": (4.5, 3.5),
}

PASSING_YARDS = {
    "Dak Prescott": (4050.5, 3850.5), "Matthew Stafford": (4000.5, 3850.5),
    "Joe Burrow": (3999.5, 3850.5), "Jared Goff": (4099.5, 4025.5),
    "Justin Herbert": (3600.5, 3500.5), "Trevor Lawrence": (3749.5, 3675.5),
    "Sam Darnold": (3749.5, 3675.5), "Drake Maye": (3800.5, 3650.5),
    "Tyler Shough": (3649.5, 3600.5), "Brock Purdy": (3850.5, 3650.5),
    "Josh Allen": (3600.5, 3475.5), "Bo Nix": (3499.5, 3350.5),
    "Caleb Williams": (3624.5, 3400.5), "Jordan Love": (3549.5, 3350.5),
    "Lamar Jackson": (3249.5, 3050.5), "C.J. Stroud": (3649.5, 3550.5),
    "Baker Mayfield": (3599.5, 3500.5), "Jalen Hurts": (3249.5, 3100.5),
    "Cam Ward": (3300.5, 3200.5), "Aaron Rodgers": (3199.5, 3025.5),
    "Jaxson Dart": (3175.5, 2950.5), "Jayden Daniels": (3399.5, 3200.5),
    "Bryce Young": (3125.5, 3000.5), "Malik Willis": (3249.5, 3050.5),
    "Fernando Mendoza": (2499.5, 2300.5),
}

PASSING_TDS = {
    "Joe Burrow": (32.5, 31.5), "Matthew Stafford": (30.5, 29.5),
    "Dak Prescott": (27.5, 26.5), "Brock Purdy": (27.5, 25.5),
    "Jared Goff": (29.5, 27.5), "Drake Maye": (26.5, 24.5),
    "Justin Herbert": (25.5, 23.5), "Josh Allen": (24.5, 23.5),
    "Trevor Lawrence": (25.5, 24.5), "Jordan Love": (24.5, 23.5),
    "Lamar Jackson": (24.5, 23.5), "Baker Mayfield": (25.5, 24.5),
    "Caleb Williams": (24.5, 23.5), "Sam Darnold": (23.5, 22.5),
    "Bo Nix": (24.5, 24.5), "C.J. Stroud": (22.5, 20.5),
    "Aaron Rodgers": (20.5, 19.5), "Jalen Hurts": (22.5, 21.5),
    "Tyler Shough": (20.5, 19.5), "Cam Ward": (19.5, 17.5),
    "Bryce Young": (20.5, 20.5), "Jayden Daniels": (22.5, 20.5),
    "Jaxson Dart": (19.5, 18.5), "Malik Willis": (15.5, 14.5),
    "Fernando Mendoza": (12.5, 11.5),
}

TE_NAMES = {
    "Brock Bowers", "Tyler Warren", "Colston Loveland", "Trey McBride",
    "Kyle Pitts Sr.", "Dallas Goedert", "Jake Ferguson", "Mark Andrews",
    "Kenyon Sadiq", "Dalton Kincaid", "Travis Kelce", "Sam LaPorta",
}
QB_NAMES = set(PASSING_YARDS) | set(PASSING_TDS)
RB_NAMES = set(RUSHING_YARDS) - QB_NAMES

# Ashton Jeanty's receiving props aren't covered by fantasypoints.com (RB
# receiving props aren't a market they track) -- kept from a user-provided
# sportsbook line (see prior session), since it's the only RB receiving line
# we have at all. Everything else in these dicts supersedes prior data.
RB_RECEIVING_OVERRIDE = {
    "Ashton Jeanty": {"rec_yards_line": 400.0, "rec_tds_line": 2.5},
}


def mid(pair):
    return round((pair[0] + pair[1]) / 2, 1)


def main():
    all_names = (set(RECEIVING_YARDS) | set(RECEIVING_TDS) | set(RUSHING_YARDS)
                 | set(RUSHING_TDS) | set(PASSING_YARDS) | set(PASSING_TDS))

    rows = []
    for name in sorted(all_names):
        if name in QB_NAMES:
            position = "QB"
        elif name in TE_NAMES:
            position = "TE"
        elif name in RB_NAMES:
            position = "RB"
        else:
            position = "WR"

        rec_yards = mid(RECEIVING_YARDS[name]) if name in RECEIVING_YARDS else None
        rec_tds = mid(RECEIVING_TDS[name]) if name in RECEIVING_TDS else None
        rush_yards = mid(RUSHING_YARDS[name]) if name in RUSHING_YARDS else None
        rush_tds = mid(RUSHING_TDS[name]) if name in RUSHING_TDS else None
        pass_yards = mid(PASSING_YARDS[name]) if name in PASSING_YARDS else None
        pass_tds = mid(PASSING_TDS[name]) if name in PASSING_TDS else None

        if position == "RB" and name in RB_RECEIVING_OVERRIDE:
            rec_yards = RB_RECEIVING_OVERRIDE[name]["rec_yards_line"]
            rec_tds = RB_RECEIVING_OVERRIDE[name]["rec_tds_line"]

        source = "fantasypoints.com season prop articles (consensus midpoint), Jun-Jul 2026"
        if name in RB_RECEIVING_OVERRIDE and position == "RB":
            source += " + user-provided sportsbook line (RB receiving, not covered by fantasypoints)"

        rows.append({
            "player_name": name, "position": position,
            "rec_yards_line": rec_yards, "rec_tds_line": rec_tds,
            "rush_yards_line": rush_yards, "rush_tds_line": rush_tds,
            "pass_yards_line": pass_yards, "pass_tds_line": pass_tds,
            "source": source,
        })

    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "vegas_player_props_2026.csv")
    fieldnames = ["player_name", "position", "rec_yards_line", "rec_tds_line",
                  "rush_yards_line", "rush_tds_line", "pass_yards_line", "pass_tds_line", "source"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})

    print(f"Wrote {len(rows)} players to {out_path}")
    print(f"  QB: {sum(1 for r in rows if r['position']=='QB')}")
    print(f"  RB: {sum(1 for r in rows if r['position']=='RB')}")
    print(f"  WR: {sum(1 for r in rows if r['position']=='WR')}")
    print(f"  TE: {sum(1 for r in rows if r['position']=='TE')}")


if __name__ == "__main__":
    main()
