for file in src/*.py *.py ; do 
    echo "==== $file ====" 
    cat "$file" 
    echo 
done > gpt_input_new.txt