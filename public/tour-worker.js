import {buildTourRoute} from './tour-route.js';
self.onmessage=({data})=>{
 try{self.postMessage({route:buildTourRoute(data.release,data.technical)})}
 catch(error){self.postMessage({error:error.message})}
};
