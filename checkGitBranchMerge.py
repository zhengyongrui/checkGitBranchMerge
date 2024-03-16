import tkinter as tk
from tkinter import filedialog, scrolledtext
from git import Repo
import re
import threading
import queue

def check_branch_merge(repo_path, branch1, branch2, keyword, queue):
    repo = Repo(repo_path)
    queue.put(f"正在拉取代码...")
    repo.remotes.origin.fetch()
    queue.put(f"拉取代码完成")
    branch1 = branch1 if branch1.startswith('origin/') else f'origin/{branch1}'
    branch2 = branch2 if branch2.startswith('origin/') else f'origin/{branch2}'

    branch1_commits = list(repo.iter_commits(branch1))
    branch2_commits = list(repo.iter_commits(branch2))

    pattern = re.compile(keyword)
    unmerged_commits = []
    merged_commits = []
    files_to_compare = set()

    queue.put(f"'{branch1}' 分支中包含关键字 '{keyword}' 的提交:")
    for commit in branch1_commits:
        if pattern.search(commit.message):
            queue.put(f"- {commit.hexsha}：{commit.message}")
            if commit not in branch2_commits:
                unmerged_commits.append(commit)
                commit_diff_files = repo.git.show('--pretty=', '--name-only', commit.hexsha).split('\n')
                files_to_compare.update(commit_diff_files)
            else:
                merged_commits.append(commit)

    if merged_commits:
        queue.put(f"以下提交包含关键字 '{keyword}' 且已从 '{branch1}' 合并到 '{branch2}':")
        for commit in merged_commits:
            queue.put(f"- {commit.hexsha}：{commit.message}")

    all_files_same = True

    for file in files_to_compare:
        if file:
            diff = repo.git.diff(f"{branch1}:{file}", f"{branch2}:{file}", '--ignore-space-at-eol', '-w', '--ignore-cr-at-eol')
            if diff:
                all_files_same = False
                queue.put(f"  - 修改的文件: {file} 在两个分支中内容不同")
            else:
                queue.put(f"  - 修改的文件: {file} 在两个分支中内容相同，可能已手工合并")

    if all_files_same:
        queue.put(f"所有包含关键字 '{keyword}' 的提交中修改的文件，在 '{branch1}' 和 '{branch2}' 之间内容相同，可能已手工合并。")
    elif unmerged_commits:
        queue.put(f"请确认以下包含关键字 '{keyword}' 但是未从 '{branch1}' 合并到 '{branch2}'的提交:")
        for commit in unmerged_commits:
            queue.put(f"- {commit.hexsha}：{commit.message}")

def browse_folder():
    folder_selected = filedialog.askdirectory()
    repo_path_entry.delete(0, tk.END)
    repo_path_entry.insert(0, folder_selected)

def run_check_branch_merge():
    repo_path = repo_path_entry.get()
    branch1 = branch1_entry.get()
    branch2 = branch2_entry.get()
    keyword = keyword_entry.get()
    output_text.delete(1.0, tk.END)
    try:
        threading.Thread(target=check_branch_merge, args=(repo_path, branch1, branch2, keyword, queue)).start()
    except Exception as e:
        queue.put(str(e))

def update_output_text():
    while not queue.empty():
        message = queue.get()
        output_text.insert(tk.END, message + "\n")
    root.after(100, update_output_text)

def on_submit():
    run_check_branch_merge()

root = tk.Tk()
root.title("Check Git Branch Merge")

queue = queue.Queue()

tk.Label(root, text="代码路径:").grid(row=0, column=0, sticky="w")
repo_path_entry = tk.Entry(root, width=200)
repo_path_entry.grid(row=0, column=1)
tk.Button(root, text="请选择...", command=browse_folder).grid(row=0, column=2)

tk.Label(root, text="源分支:").grid(row=1, column=0, sticky="w")
branch1_entry = tk.Entry(root)
branch1_entry.grid(row=1, column=1, columnspan=2, sticky="ew")

tk.Label(root, text="目标分支:").grid(row=2, column=0, sticky="w")
branch2_entry = tk.Entry(root)
branch2_entry.grid(row=2, column=1, columnspan=2, sticky="ew")

tk.Label(root, text="提交关键字:").grid(row=3, column=0, sticky="w")
keyword_entry = tk.Entry(root)
keyword_entry.grid(row=3, column=1, columnspan=2, sticky="ew")

submit_button = tk.Button(root, text="检查合并", command=on_submit)
submit_button.grid(row=4, column=0, columnspan=3)

output_text = scrolledtext.ScrolledText(root, height=50)
output_text.grid(row=10, column=0, columnspan=3, sticky="ew")

update_output_text()

root.mainloop()