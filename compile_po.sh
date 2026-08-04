#!/bin/bash
LOCALE_DIR="locales"

# Check if msgfmt is available
if ! command -v msgfmt &> /dev/null
then
    echo "msgfmt command not found. Please install gettext utilities."
    echo "On Debian/Ubuntu: sudo apt-get install gettext"
    echo "On macOS with Homebrew: brew install gettext"
    exit 1
fi

echo "Compiling .po files to .mo files..."

for lang_dir in "$LOCALE_DIR"/*; do
    if [ -d "$lang_dir" ]; then
        lang_code=$(basename "$lang_dir")
        lc_messages_dir="$lang_dir/LC_MESSAGES"
        po_file="$lc_messages_dir/messages.po"
        mo_file="$lc_messages_dir/messages.mo"

        if [ -f "$po_file" ]; then
            echo "Compiling $po_file to $mo_file"
            msgfmt "$po_file" -o "$mo_file"
            if [ $? -eq 0 ]; then
                echo "Successfully compiled $lang_code."
            else
                echo "Error compiling $lang_code."
            fi
        else
            echo "No messages.po found for $lang_code at $po_file"
        fi
    fi
done

echo "Compilation complete."
