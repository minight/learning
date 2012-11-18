/* 
 * File:   For Loops Total and Average.cpp
 * Author: S2XY
 *
 * Created on 17 November 2012, 8:33 PM
 */
#include <iostream>
#include <iomanip>


using namespace std;

int main(){
    int choice = 0, i, total, j = 0 ;
    double avg = 0;
    
    cout << "enter a number between 1 and 1776";
    cin >> choice;
    
    while( choice < i || choice > 1776){
        cout << "please enter a valid value, between 1 and 1776: ";
        cin >> choice;
    }
    for (i = 1776; i> choice ; i--){
        total += i;
        cout << setw(8) << i;
        j++;
    }
    avg = total / double(j);
    cout << endl << endl;
    cout << "Numbers Output: "<< j << endl<< "Total of Numbers OUtput: " << total << endl;
    cout << "average of numbers output: " << avg; 
    
}