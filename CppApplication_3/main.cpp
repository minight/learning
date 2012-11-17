#include <iostream>
#include <cmath>
//Learning Nested Loops or Nested For Loops.
using namespace std;
int main(){
    int choice = 0, i , j;
   
    cout << "how many digits do you want to use: ";
    cin >> choice;
    
    for(i=1; i <= choice; i++){ //outer loop
        for(j=1; j <= i; j++){ //inner loop
            cout << j;
        }//end inner loop
        cout << endl;
    }//end outer loop
    
    for(i=choice; i>= 0; i--){
        for(j=1; j< i; j++){
            cout << j;
        }
        cout << endl;
    }
    
    
    return 0;
}