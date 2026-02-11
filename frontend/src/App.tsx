import "./App.css";

import { Route, Routes } from "react-router-dom";

import CreateRoute from "./screens/Create";
import NewScreen from "./screens/New";

const App: React.FC = () => {
  return (
    <div className="bg-background text-foreground flex flex-col items-center justify-start w-screen h-screen overflow-hidden">
      <div className="w-full flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<NewScreen />} />
          <Route path="/p/:slug" element={<CreateRoute />} />
          <Route path="/create" element={<CreateRoute />} />
        </Routes>
      </div>
      <footer className="w-full shrink-0 border-t border-border/60 bg-background/95 px-4 py-2 text-center text-xs text-muted-foreground">
        Made with Love by Mayflower, with the help of Langchain, Hasura, React
      </footer>
    </div>
  );
};

export default App;
