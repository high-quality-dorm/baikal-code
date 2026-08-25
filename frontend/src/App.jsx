import { Navigate, Route, Routes } from "react-router-dom";
import Landing from "./pages/Landing.jsx";
import Chat from "./pages/Chat.jsx";
import Login from "./pages/Login.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/chat" element={<Chat />} />
      <Route path="/login" element={<Login />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}