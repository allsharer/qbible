"""Shell completion scripts (installed to /usr/share/bash-completion/completions/qbible)."""

BASH_COMPLETION = r"""# bash completion for qbible                                  -*- shell-script -*-
_qbible()
{
    local cur prev words cword
    if declare -F _init_completion >/dev/null 2>&1; then
        _init_completion || return
    else
        cur="${COMP_WORDS[COMP_CWORD]}"; prev="${COMP_WORDS[COMP_CWORD-1]}"
        words=("${COMP_WORDS[@]}"); cword=$COMP_CWORD
    fi

    local commands="read chapter next previous prev random books search ref bookmark bookmarks history
        shell interactive serve translations import remove-translation validate config paths completion"
    local global="-t --translation --colour --plain --no-colour -h --help -V --version"

    case "$prev" in
        -t|--translation|remove-translation)
            COMPREPLY=($(compgen -W "$(qbible translations --json 2>/dev/null | sed -n 's/^ *"id": "\(.*\)",$/\1/p')" -- "$cur"))
            return ;;
        --colour|--color) COMPREPLY=($(compgen -W "auto always never" -- "$cur")); return ;;
        --testament) COMPREPLY=($(compgen -W "OT NT" -- "$cur")); return ;;
        --sort) COMPREPLY=($(compgen -W "canonical relevance" -- "$cur")); return ;;
        --supplied) COMPREPLY=($(compgen -W "plain brackets italic" -- "$cur")); return ;;
        --format) COMPREPLY=($(compgen -W "vpl tsv" -- "$cur")); return ;;
    esac

    local cmd="" i
    for ((i = 1; i < cword; i++)); do
        case "${words[i]}" in
            -t|--translation|--colour|--color) ((i++)) ;;
            -*) ;;
            *) cmd="${words[i]}"; break ;;
        esac
    done

    if [[ -z "$cmd" ]]; then
        COMPREPLY=($(compgen -W "$commands $global" -- "$cur"))
        return
    fi

    local books="Genesis Exodus Leviticus Numbers Deuteronomy Joshua Judges Ruth 1Samuel 2Samuel
        1Kings 2Kings 1Chronicles 2Chronicles Ezra Nehemiah Esther Job Psalm Psalms Proverbs
        Ecclesiastes Song_of_Solomon Isaiah Jeremiah Lamentations Ezekiel Daniel Hosea Joel Amos
        Obadiah Jonah Micah Nahum Habakkuk Zephaniah Haggai Zechariah Malachi Matthew Mark Luke
        John Acts Romans 1Corinthians 2Corinthians Galatians Ephesians Philippians Colossians
        1Thessalonians 2Thessalonians 1Timothy 2Timothy Titus Philemon Hebrews James 1Peter 2Peter
        1John 2John 3John Jude Revelation"
    local reading="-n --numbers -N --no-numbers --supplied --pilcrows --no-heading --no-wrap --no-history --json"
    case "$cmd" in
        read|chapter)
            if [[ "$cur" == -* ]]; then COMPREPLY=($(compgen -W "$reading $global" -- "$cur"))
            else COMPREPLY=($(compgen -W "$books" -- "$cur")); COMPREPLY=("${COMPREPLY[@]//_/ }"); fi ;;
        next|previous|prev) COMPREPLY=($(compgen -W "--from $reading" -- "$cur")) ;;
        search) COMPREPLY=($(compgen -W "--phrase --words --any -l --limit -p --page -c --context --sort --book --testament --count $reading" -- "$cur")) ;;
        bookmark|bookmarks) COMPREPLY=($(compgen -W "add list open label remove --label --json" -- "$cur")) ;;
        history) COMPREPLY=($(compgen -W "list clear --limit --json" -- "$cur")) ;;
        config) COMPREPLY=($(compgen -W "list get set unset reading.translation reading.verse_numbers reading.supplied reading.pilcrows display.colour search.limit server.host server.port" -- "$cur")) ;;
        serve) COMPREPLY=($(compgen -W "--host --port --open --allow-remote --no-user-data" -- "$cur")) ;;
        random|books) COMPREPLY=($(compgen -W "--testament --json" -- "$cur")) ;;
        import) COMPREPLY=($(compgen -f -W "--id --name --licence --format --abbreviation --language --copyright --attribution --source-name --source-url --retrieved --versification --force" -- "$cur")) ;;
        *) COMPREPLY=($(compgen -W "--json --help" -- "$cur")) ;;
    esac
} &&
complete -F _qbible qbible
"""
