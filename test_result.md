#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================


#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: "Enhance DUALSPORT MAPS backend with advanced route planning modules for dirt discovery, DEM analysis, imagery validation, and popularity tracking to provide comprehensive ADV route intelligence."

backend:
  - task: "Enhanced Overpass Query Builder"
    implemented: true
    working: "NA"  
    file: "modules/overpass_enhanced.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      -working: "NA"
      -agent: "main"
      -comment: "Implemented comprehensive Overpass API client with bbox tiling, retry logic, surface scoring, and anchor via generation. Ready for testing."

  - task: "DEM Analysis Module"
    implemented: true
    working: "NA"
    file: "modules/dem_analysis.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      -working: "NA"
      -agent: "main"
      -comment: "Implemented DEM analysis with Mapbox Terrain-RGB integration, grade calculations, ridge scoring, and washout detection. Ready for testing."

  - task: "Imagery Validation Module"
    implemented: true
    working: "NA"
    file: "modules/imagery_validation.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      -working: "NA"
      -agent: "main"
      -comment: "Implemented imagery validation with Mapillary integration, surface verification, and confidence scoring. Ready for testing."

  - task: "Popularity Tracking Module"
    implemented: true
    working: "NA"
    file: "modules/popularity_tracker.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      -working: "NA"
      -agent: "main"
      -comment: "Implemented popularity tracking with Wikiloc integration, GPX processing, and SQLite caching. Ready for testing."

  - task: "Enhanced Route Planner Core"
    implemented: true
    working: "NA"
    file: "modules/route_planner_enhanced.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      -working: "NA"
      -agent: "main"
      -comment: "Implemented master route planner that orchestrates all analysis modules with parallel processing and comprehensive diagnostics. Ready for testing."

  - task: "FastAPI Integration"
    implemented: true
    working: "NA"
    file: "server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      -working: "NA"
      -agent: "main"
      -comment: "Integrated enhanced modules into FastAPI with new /api/route/advanced endpoint, environment variables, and error handling. Ready for testing."

  - task: "Environment Variables Setup"
    implemented: true
    working: "NA"
    file: ".env"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
      -working: "NA"
      -agent: "main"
      -comment: "Added placeholders for MAPBOX_TOKEN, MAPILLARY_TOKEN, and WIKILOC_TOKEN in .env file. Features gracefully degrade when tokens are not provided."

frontend:
  - task: "No frontend changes required"
    implemented: true
    working: true
    file: "N/A"
    stuck_count: 0
    priority: "low"
    needs_retesting: false
    status_history:
      -working: true
      -agent: "main"
      -comment: "This is backend-only enhancement work. Existing frontend should continue working with existing /api/route/enhanced endpoint."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 1
  run_ui: false

test_plan:
  current_focus:
    - "Enhanced Route Planner Core"
    - "FastAPI Integration"
    - "Enhanced Overpass Query Builder"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  -agent: "main"
  -message: "Backend enhancement complete. Implemented 5 new modules for advanced ADV route planning: overpass queries, DEM analysis, imagery validation, popularity tracking, and master planner. Added new /api/route/advanced endpoint. All modules have comprehensive error handling and graceful degradation when API tokens are missing. Ready for backend testing."