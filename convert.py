# Given a python file, easily convert it to something capable of being eval'd by the bot
with open("code.py", "r") as i:
    contents = i.read()

with open("code_out.txt", "w") as o:
    o.write("|".join(contents.split("\n")))
