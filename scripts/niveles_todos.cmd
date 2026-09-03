@echo off
set PYTHONIOENCODING=utf-8
set PY=C:\Users\Pablo\Documents\birdcast-europa\.venv\Scripts\python.exe
cd /d C:\Users\Pablo\Documents\birdcast-europa
%PY% -m birdcast_eu.cli meteo-niveles estjv esgld essft esahr ptprt ptflr ptsmg
%PY% -m birdcast_eu.cli meteo-niveles
echo FIN
