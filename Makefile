# Smart Plug Calendar Controller - Makefile

.PHONY: help setup build up down logs test clean restart

# Default target
help:
	@echo "Smart Plug Calendar Controller"
	@echo ""
	@echo "Available commands:"
	@echo "  setup    - Run initial setup script"
	@echo "  build    - Build Docker containers"
	@echo "  up       - Start the application"
	@echo "  down     - Stop the application"
	@echo "  logs     - View application logs"
	@echo "  test     - Run test suite"
	@echo "  restart  - Restart the application"
	@echo "  clean    - Clean up Docker resources"
	@echo "  once     - Run a single check (not continuous)"

# Setup
setup:
	python3 setup.py

# Docker commands
build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

restart:
	docker-compose restart

# Logging
logs:
	docker-compose logs -f

logs-tail:
	docker-compose logs --tail=50 -f

# Testing
test:
	python3 test_setup.py

# Run once
once:
	docker-compose run --rm smart-plug-calendar python smart_plug_calendar.py --once

# Cleanup
clean:
	docker-compose down --remove-orphans
	docker system prune -f

# Full rebuild
rebuild: down clean build up

# Development
dev:
	docker-compose -f docker-compose.yml -f docker-compose.override.yml up --build

# Status
status:
	docker-compose ps
	@echo ""
	@echo "Container logs (last 10 lines):"
	docker-compose logs --tail=10 smart-plug-calendar

