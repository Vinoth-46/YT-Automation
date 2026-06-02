import json
import os

notebook_path = "kaggle_notebook.ipynb"

if not os.path.exists(notebook_path):
    print(f"Error: {notebook_path} not found.")
    exit(1)

with open(notebook_path, "r", encoding="utf-8") as f:
    data = json.load(f)

modified = False

for cell in data.get("cells", []):
    if cell.get("cell_type") == "code":
        source = cell.get("source", [])
        source_str = "".join(source)
        
        # Check if this is Cell 6 (contains run_kaggle_bot and BotCommand)
        if "async def run_kaggle_bot():" in source_str and "BotCommand(" in source_str:
            print("Found Cell 6 inside notebook. Modifying...")
            
            # 1. Update imports
            old_import = '    start_command, status_command, generate_command,\n    schedule_command, view_schedule_command, cancel_command, button_callback\n'
            new_import = '    start_command, status_command, generate_command,\n    schedule_command, view_schedule_command, clear_schedule_command,\n    autopost_command, cancel_command, button_callback\n'
            
            # Since JSON source might have individual lines, let's do a join and replace in string, then split back to lines
            new_source_str = source_str
            
            # Update the specific block of imports
            target_imports = (
                "from bot.handlers import (\n"
                "    start_command, status_command, generate_command,\n"
                "    schedule_command, view_schedule_command, cancel_command, button_callback\n"
                ")"
            )
            replacement_imports = (
                "from bot.handlers import (\n"
                "    start_command, status_command, generate_command,\n"
                "    schedule_command, view_schedule_command, clear_schedule_command,\n"
                "    autopost_command, cancel_command, button_callback\n"
                ")"
            )
            new_source_str = new_source_str.replace(target_imports, replacement_imports)
            
            # 2. Update bot commands
            target_commands = (
                '    commands = [\n'
                '        BotCommand("start", "Start the bot and get welcome message"),\n'
                '        BotCommand("generate", "Generate a new video now"),\n'
                '        BotCommand("status", "Check recent job status"),\n'
                '        BotCommand("schedule", "Set daily posting time (UTC)"),\n'
                '        BotCommand("view_schedule", "View active schedules"),\n'
                '        BotCommand("cancel", "Cancel current process")\n'
                '    ]'
            )
            replacement_commands = (
                '    commands = [\n'
                '        BotCommand("start", "Start the bot and get welcome message"),\n'
                '        BotCommand("generate", "Generate a new video now"),\n'
                '        BotCommand("status", "Check recent job status"),\n'
                '        BotCommand("schedule", "Set daily posting time (IST)"),\n'
                '        BotCommand("view_schedule", "View active schedules"),\n'
                '        BotCommand("clearschedule", "Revoke/Clear all active schedules"),\n'
                '        BotCommand("autopost", "Toggle auto-approval mode (on/off)"),\n'
                '        BotCommand("cancel", "Cancel current process")\n'
                '    ]'
            )
            new_source_str = new_source_str.replace(target_commands, replacement_commands)
            
            # 3. Update scheduler initialization to include bot instance
            target_scheduler = (
                '        from core.scheduler import SchedulerService\n'
                '        scheduler = SchedulerService()\n'
            )
            replacement_scheduler = (
                '        from core.scheduler import SchedulerService\n'
                '        scheduler = SchedulerService(bot=application.bot)\n'
            )
            new_source_str = new_source_str.replace(target_scheduler, replacement_scheduler)
            
            # 4. Update handler registrations
            target_handlers = (
                "    application.add_handler(CommandHandler('start', start_command))\n"
                "    application.add_handler(CommandHandler('status', status_command))\n"
                "    application.add_handler(CommandHandler('generate', generate_command))\n"
                "    application.add_handler(CommandHandler('schedule', schedule_command))\n"
                "    application.add_handler(CommandHandler('view_schedule', view_schedule_command))\n"
                "    application.add_handler(CommandHandler('cancel', cancel_command))\n"
                "    application.add_handler(CallbackQueryHandler(button_callback))"
            )
            replacement_handlers = (
                "    application.add_handler(CommandHandler('start', start_command))\n"
                "    application.add_handler(CommandHandler('status', status_command))\n"
                "    application.add_handler(CommandHandler('generate', generate_command))\n"
                "    application.add_handler(CommandHandler('schedule', schedule_command))\n"
                "    application.add_handler(CommandHandler('view_schedule', view_schedule_command))\n"
                "    application.add_handler(CommandHandler('clearschedule', clear_schedule_command))\n"
                "    application.add_handler(CommandHandler('autopost', autopost_command))\n"
                "    application.add_handler(CommandHandler('cancel', cancel_command))\n"
                "    application.add_handler(CallbackQueryHandler(button_callback))"
            )
            new_source_str = new_source_str.replace(target_handlers, replacement_handlers)
            
            # Re-split into lines keeping newlines as items (exactly as Jupyter notebook source)
            new_lines = []
            current_line = ""
            for char in new_source_str:
                current_line += char
                if char == "\n":
                    new_lines.append(current_line)
                    current_line = ""
            if current_line:
                new_lines.append(current_line)
                
            cell["source"] = new_lines
            modified = True

if modified:
    with open(notebook_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    print("✅ kaggle_notebook.ipynb successfully modified and saved!")
else:
    print("❌ No modifications were made. Check source targets.")
