# Product Brief: Simple To-Do List App

## Overview
Build a basic to-do list application that allows users to create, read, update, and delete tasks.

## Requirements
1. **User Interface**: Simple web-based interface built with React
2. **Features**:
   - Add new tasks with title and description
   - Mark tasks as complete/incomplete
   - Edit a task's title
   - Delete tasks
   - Filter tasks by status (all, active, completed)
3. **Data Storage**: Local storage
4. **No authentication required**

## Interface
- A text field labelled "Title", a text area labelled "Description", and a button named "Add task".
- A task cannot be added without a title.
- Each task is an item of a list and shows its title and description.
- Each task has a checkbox labelled "Done" that marks it complete or incomplete.
- Each task has a button named "Edit". It shows a text field labelled "Edit title" and a button named "Save" that saves the new title.
- Each task has a button named "Delete" that removes it.
- Three buttons named "All", "Active" and "Completed" filter the list.

## Technical Constraints
- Single-page application
- React with TypeScript, built with Vite
- Should work in modern browsers
- Maximum 500 lines of code

## Acceptance Criteria
- Users can add, edit, delete tasks
- Tasks persist between page refreshes
- Filter functionality works correctly
- Responsive design for mobile and desktop
