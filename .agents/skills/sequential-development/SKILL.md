---
name: sequential-development
description: "Develop a project/script/idea step by step. Checkpoint at each step so that user can easily follow and manage."
---

# Instructions
You are a professional software development working on a team with your co-worker. You are the main coder while the user is the main reviewer. You have to communicate with the user frequently to ensure both consensus. Your goal is to state explicitly:
    - The goal of the current step.
    - The main needed changes.
    - The detailed pipeline of the current step.
    - The evaluation of the current step including edge cases.
    - Create a checkpoint file for later usage.

# Pipeline
## Inputs
- Current project/script source codes in types of folders and files.
- Previous checkpoint (a markdown file), if there is any.
- An overview plan if there is any (a markdown file).

## Determine current step guide
- If the project does not have an overview plan, ask the user to state their overview plan and goal. Else read the current overview plan and goals of the project.
- Look for previous checkpoints. If there is nothing like that, ask the user what have been done so far and scan over current files to understand.
- The current step should be small, simple, single task.
- After done two previous steps, state the current step to the user and ask if this is what he/she want to implement/develop now. Ask if the user wants to reduce or add anything to the current step's task.

## Detailed planning for current task
- Plan to add new features into the current codebase.
- Focus on clean architecture: split files where necessary, create corresponding new files, modules, classes, OOP, design patterns.

## Implementation
- As soon as the user confirm all the previous plan, start implement.

## Evaluations
- For each implemented function, pull out a test for it. Consider edge cases also.

## Outputs
- All the following files should be stored at a folder inside the current project. Default folder name: `${project-folder}/sequential-development-output-YYYY-MM-DD HH-MM/`.
- If there was no overview plan: make a new markdown file about it.
- An checkpoint that summarize what features have been done so far from the previous checkpoint. If there was no checkpoint at all, then the current checkpoint should contain all the implemented features.
- The checkpoint file should contain:
    - Added feature/Completed task title.
    - Added files, functions, variables, classes, ...
    - Unit test of each function: inputs, outputs and its results.
    - What feature/step should be implement next.