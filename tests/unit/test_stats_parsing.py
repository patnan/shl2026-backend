"""Unit tests for stats_parsing module."""
import pytest

from src.shl.helpers.stats_parsing import (
    parse_leading_goalies,
    parse_scoring_leaders,
    parse_team_rosters,
)


SCORING_LEADERS_HTML = """
<html><body>
<table class="tblContent">
<tr><td>Scoring Leaders</td><td>Last update: 2026-03-23 17:25</td><td></td></tr>
<tr><td>Rk</td><td>No</td><td>Name</td><td>Team</td><td>Pos</td><td>GP</td><td>G</td><td>A</td><td>TP</td><td>AVG.</td><td>PIM</td><td>+/-</td></tr>
<tr><td>1</td><td>24</td><td>Lindberg, Oscar</td><td>SKE</td><td>CE</td><td>52</td><td>30</td><td>37</td><td>67</td><td>1.29</td><td>52</td><td>53:36</td></tr>
<tr><td>2</td><td>96</td><td>Hugg, Rickard</td><td>SKE</td><td>CE</td><td>52</td><td>20</td><td>36</td><td>56</td><td>1.08</td><td>12</td><td>50:37</td></tr>
<tr><td>3</td><td>54</td><td>Dahlén, Jonathan</td><td>TIK</td><td>LW</td><td>50</td><td>30</td><td>25</td><td>55</td><td>1.10</td><td>16</td><td>39:30</td></tr>
</table>
</body></html>
"""

LEADING_GOALIES_HTML = """
<html><body>
<table class="tblContent">
<tr><td>Leading Goalies by Saves Percentage</td><td>Last update: 2026-03-23 17:25</td><td></td></tr>
<tr><td>Rk</td><td>No</td><td>Name</td><td>Team</td><td>GP</td><td>GPI</td><td>MIP</td><td>SOG</td><td>GA</td><td>GAA</td><td>SVS</td><td>SVS%</td><td>SO</td><td>W</td><td>L</td><td>W%</td></tr>
<tr><td>1</td><td>30</td><td>Normann, Tobias</td><td>FRÖ</td><td>52</td><td>24</td><td>1425:53</td><td>522</td><td>40</td><td>1.68</td><td>482</td><td>92.34</td><td>3</td><td>14</td><td>10</td><td>58,33</td></tr>
<tr><td>2</td><td>38</td><td>Mann, Strauss</td><td>SKE</td><td>51</td><td>42</td><td>2483:18</td><td>925</td><td>80</td><td>1.93</td><td>845</td><td>91.35</td><td>10</td><td>31</td><td>10</td><td>75,61</td></tr>
<tr><td></td><td>61</td><td>Delia, Collin</td><td>BIF</td><td>29</td><td>6</td><td>340:39</td><td>105</td><td>22</td><td>3.87</td><td>83</td><td>79.05</td><td>0</td><td>1</td><td>4</td><td>20,00</td></tr>
</table>
</body></html>
"""

TEAM_ROSTER_HTML = """
<html><body>
<table class="tblContent">
<tr><th>Brynäs IF</th><th>Brynäs IF</th><th>[Top]</th></tr>
<tr><td>Team Roster</td><td>Team Roster</td></tr>
<tr><td>No</td><td>Name</td><td>Birthdate</td><td>Position</td><td>L/R</td><td>Height</td><td>Weight</td><td>Nationality / Club</td><td>Youth club</td></tr>
<tr><td>3</td><td>Djoos, Christian</td><td>1994-08-06</td><td>RD</td><td>L</td><td>181</td><td>82</td><td>SWE</td><td>Brynäs IF</td></tr>
<tr><td>5</td><td>Kempny, Michal</td><td>1990-09-08</td><td>LD</td><td>L</td><td>183</td><td>89</td><td>CZE</td><td>HC Kometa Brno</td></tr>
</table>
<table class="tblContent">
<tr><th>Brynäs IF</th><th>Brynäs IF</th><th>[Top]</th></tr>
<tr><td>Team Roster</td><td>Team Roster</td></tr>
<tr><td>No</td><td>Name</td><td>Birthdate</td><td>Position</td><td>L/R</td><td>Height</td><td>Weight</td><td>Nationality / Club</td><td>Youth club</td></tr>
<tr><td>3</td><td>Djoos, Christian</td><td>1994-08-06</td><td>RD</td><td>L</td><td>181</td><td>82</td><td>SWE</td><td>Brynäs IF</td></tr>
<tr><td>5</td><td>Kempny, Michal</td><td>1990-09-08</td><td>LD</td><td>L</td><td>183</td><td>89</td><td>CZE</td><td>HC Kometa Brno</td></tr>
</table>
<table class="tblContent">
<tr><th>Team Officials</th><th>Title</th><th>Name</th></tr>
<tr><td>Head Coach</td><td>Karlsson, Peter</td></tr>
</table>
<table class="tblContent">
<tr><th>Frölunda HC</th><th>Frölunda HC</th><th>[Top]</th></tr>
<tr><td>Team Roster</td><td>Team Roster</td></tr>
<tr><td>No</td><td>Name</td><td>Birthdate</td><td>Position</td><td>L/R</td><td>Height</td><td>Weight</td><td>Nationality / Club</td><td>Youth club</td></tr>
<tr><td>30</td><td>Normann, Tobias</td><td>1998-03-15</td><td>GK</td><td>L</td><td>185</td><td>88</td><td>SWE</td><td>Frölunda HC</td></tr>
</table>
</body></html>
"""


class TestParseScoringLeaders:
    def test_parses_all_players(self):
        result = parse_scoring_leaders(SCORING_LEADERS_HTML)
        assert len(result) == 3

    def test_first_player_fields(self):
        result = parse_scoring_leaders(SCORING_LEADERS_HTML)
        p = result[0]
        assert p.rank == 1
        assert p.jersey == 24
        assert p.name == "Lindberg, Oscar"
        assert p.team == "SKE"
        assert p.position == "CE"
        assert p.games_played == 52
        assert p.goals == 30
        assert p.assists == 37
        assert p.total_points == 67
        assert p.points_per_game == 1.29
        assert p.penalty_minutes == 52
        assert p.plus_minus == 17  # 53 - 36

    def test_plus_minus_calculation(self):
        result = parse_scoring_leaders(SCORING_LEADERS_HTML)
        assert result[0].plus_minus == 17   # 53-36
        assert result[1].plus_minus == 13   # 50-37
        assert result[2].plus_minus == 9    # 39-30

    def test_empty_html_returns_empty(self):
        assert parse_scoring_leaders("<html><body></body></html>") == []


class TestParseLeadingGoalies:
    def test_parses_all_goalies(self):
        result = parse_leading_goalies(LEADING_GOALIES_HTML)
        assert len(result) == 3

    def test_first_goalie_fields(self):
        result = parse_leading_goalies(LEADING_GOALIES_HTML)
        g = result[0]
        assert g.rank == 1
        assert g.jersey == 30
        assert g.name == "Normann, Tobias"
        assert g.team == "FRÖ"
        assert g.games_played == 52
        assert g.games_played_in == 24
        assert g.minutes_in_play == "1425:53"
        assert g.shots_on_goal == 522
        assert g.goals_against == 40
        assert g.goals_against_avg == 1.68
        assert g.saves == 482
        assert g.save_percentage == 92.34
        assert g.shutouts == 3
        assert g.wins == 14
        assert g.losses == 10
        assert g.win_percentage == 58.33

    def test_comma_decimal_win_percentage(self):
        result = parse_leading_goalies(LEADING_GOALIES_HTML)
        # "58,33" should parse as 58.33
        assert result[0].win_percentage == 58.33
        assert result[1].win_percentage == 75.61

    def test_empty_rank_gets_sequential_number(self):
        result = parse_leading_goalies(LEADING_GOALIES_HTML)
        # Third goalie has empty rank cell, should get rank 3
        assert result[2].rank == 3
        assert result[2].name == "Delia, Collin"

    def test_empty_html_returns_empty(self):
        assert parse_leading_goalies("<html><body></body></html>") == []


class TestParseTeamRosters:
    def test_parses_players_from_multiple_teams(self):
        result = parse_team_rosters(TEAM_ROSTER_HTML)
        teams = set(r.team for r in result)
        assert teams == {"Brynäs IF", "Frölunda HC"}

    def test_deduplicates_tables(self):
        # Brynäs IF appears twice in the HTML (duplicate tables)
        result = parse_team_rosters(TEAM_ROSTER_HTML)
        bif_players = [r for r in result if r.team == "Brynäs IF"]
        assert len(bif_players) == 2  # Only 2, not 4

    def test_first_player_fields(self):
        result = parse_team_rosters(TEAM_ROSTER_HTML)
        bif = [r for r in result if r.team == "Brynäs IF"]
        p = bif[0]
        assert p.team == "Brynäs IF"
        assert p.jersey == 3
        assert p.name == "Djoos, Christian"
        assert p.birthdate == "1994-08-06"
        assert p.position == "RD"
        assert p.handedness == "L"
        assert p.height == 181
        assert p.weight == 82
        assert p.nationality == "SWE"
        assert p.youth_club == "Brynäs IF"

    def test_skips_team_officials_table(self):
        result = parse_team_rosters(TEAM_ROSTER_HTML)
        names = [r.name for r in result]
        assert "Karlsson, Peter" not in names

    def test_empty_html_returns_empty(self):
        assert parse_team_rosters("<html><body></body></html>") == []
