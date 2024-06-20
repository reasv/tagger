from __future__ import annotations
from typing import List
import json
from urllib.parse import quote

import gradio as gr
from src.ui.components.utils import delete_bookmarks_except_last_n, get_all_bookmarks_in_folder, delete_bookmark
from src.ui.components.bookmark_folder_selector import create_bookmark_folder_chooser # type: ignore
from src.ui.components.multi_view import create_multiview
from src.db import FileSearchResult

def get_bookmarks_paths(bookmarks_namespace: str, order_by: str = "time_added", order: str = None):
    if order == "default":
        order = None
    bookmarks, total_bookmarks = get_all_bookmarks_in_folder(bookmarks_namespace, order_by=order_by, order=order)
    print(f"Bookmarks fetched from {bookmarks_namespace} folder. Total: {total_bookmarks}, Displayed: {len(bookmarks)}")
    return bookmarks

def erase_bookmarks_fn(bookmarks_namespace: str, keep_last_n: int, order_by: str = "time_added", order: str = None):
    delete_bookmarks_except_last_n(bookmarks_namespace, keep_last_n)
    print("Bookmarks erased")
    bookmarks = get_bookmarks_paths(bookmarks_namespace, order_by=order_by, order=order)
    return bookmarks

def delete_bookmark_fn(bookmarks_namespace: str, selected_files: List[FileSearchResult], order_by: str = "time_added", order: str = None):
    if len(selected_files) == 0:
        print("No bookmark selected")
        return
    delete_bookmark(bookmarks_namespace=bookmarks_namespace, sha256=selected_files[0].sha256)
    print("Bookmark deleted")
    bookmarks = get_bookmarks_paths(bookmarks_namespace, order_by=order_by, order=order)
    return bookmarks

def build_bookmark_query(bookmarks_namespace: str, page_size: int = 1000, page: int = 1, order_by: str = "time_added", order: str = None):
    order_str = f"&order={order}" if order else ""
    return f"/bookmarks/{bookmarks_namespace}?order_by={order_by}{order_str}"

def bookmark_query_text(bookmarks_namespace: str, page_size: int = 1000, page: int = 1, order_by: str = "time_added", order: str = None):
    if order == "default":
        order = None
    return f"[View Bookmark folder in Gallery]({build_bookmark_query(bookmarks_namespace, page_size=page_size, page=page, order_by=order_by, order=order)})"

def create_bookmarks_UI(bookmarks_namespace: gr.State):
    secondary_namespace = gr.State("default")
    with gr.TabItem(label="Bookmarks") as bookmarks_tab:
        with gr.Column(elem_classes="centered-content", scale=0):
            with gr.Row():
                link = gr.Markdown(bookmark_query_text("default"))
                create_bookmark_folder_chooser(parent_tab=bookmarks_tab, bookmarks_namespace=bookmarks_namespace)
                with gr.Column():
                    order_by = gr.Radio(choices=["time_added", "path", "last_modified"], label="Order by", value="time_added")
                    order = gr.Radio(choices=["asc", "desc", "default"], value="default", show_label=False)
                erase_bookmarks = gr.Button("Erase bookmarks")
                keep_last_n = gr.Slider(minimum=0, maximum=100, value=0, step=1, label="Keep last N items on erase")

        multi_view = create_multiview(bookmarks_namespace=secondary_namespace, extra_actions=["Remove From Current Group"])

    bookmarks_tab.select(
        fn=get_bookmarks_paths,
        inputs=[bookmarks_namespace, order_by, order],
        outputs=[multi_view.files]
    )

    bookmarks_namespace.change(
        fn=get_bookmarks_paths,
        inputs=[bookmarks_namespace, order_by, order],
        outputs=[
            multi_view.files
        ]
    )

    order_by.change(
        fn=get_bookmarks_paths,
        inputs=[bookmarks_namespace, order_by, order],
        outputs=[
            multi_view.files
        ]
    )
    order.change(
        fn=get_bookmarks_paths,
        inputs=[bookmarks_namespace, order_by, order],
        outputs=[
            multi_view.files
        ]
    )

    # Update link to gallery view
    bookmarks_namespace.change(
        fn=bookmark_query_text,
        inputs=[bookmarks_namespace, order_by, order],
        outputs=[link]
    )

    erase_bookmarks.click(
        fn=erase_bookmarks_fn,
        inputs=[bookmarks_namespace, keep_last_n, order_by, order],
        outputs=[
            multi_view.files
        ]
    )

    multi_view.list_view.extra[0].click(
        fn=delete_bookmark_fn,
        inputs=[bookmarks_namespace, multi_view.selected_files, order_by, order],
        outputs=[
            multi_view.files
        ]
    )

    multi_view.gallery_view.extra[0].click(
        fn=delete_bookmark_fn,
        inputs=[bookmarks_namespace, multi_view.selected_files, order_by, order],
        outputs=[
            multi_view.files
        ]
    )
