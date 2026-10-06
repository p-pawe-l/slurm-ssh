TESTS_DIRECTORY := tests 

test: 
	python -m unittest discover -s $(TESTS_DIRECTORY) -p "test_*.py"

PHONY: test