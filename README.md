HPL3 Exporter Develop Branch
==============================================================================
![](https://i.imgur.com/1PrPPuD.jpg)

Setup - Requires Blender 2.8 or later, and a Windows Bash shell with
	core utilities such as 'md5sum', and optionally 'magick' command to test
	texture similarity, which is more forgiving for images with very slight
	differences)
------------------------------------------------------------------------------
- At the top of io_export_hpl3_integration_tests/integrationtest.sh, set your
Blender install path

- Run [ ./integrationtest.sh ] to run all tests

- Run [ ./integrationtest.sh approve ] to set all tests to passing

- Make your changes

- Run tests individually [ ./integrationtest.sh TESTNAME ], with or without arguments

- [ ./integrationtest.sh TESTNAME build ] to set up a Blender file you can modify,
	then save as a test to be run

- [ ./integrationtest.sh TESTNAME gui ] to launch Blender after the script ran
	(useful for when the script crashes, and you want to see the state at crash time)

- [ ./integrationtest.sh TESTNAME approve ] - To set a test as 'succeeding', once you have
	visually inspected files to be in good shape
