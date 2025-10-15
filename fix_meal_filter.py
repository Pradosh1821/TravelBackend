import re

# Read the file
with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the problematic meal filtering logic
old_pattern = r'if activity\.get\("meal"\) in \["Breakfast", "Lunch", "Dinner"\]:'
new_pattern = 'if activity.get("meal"):'

# Replace all occurrences
content = re.sub(old_pattern, new_pattern, content)

# Write back to file
with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed meal filtering logic in main.py")